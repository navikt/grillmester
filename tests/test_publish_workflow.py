from __future__ import annotations

import gzip
import io
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/publish-marketplace.yml"
PROMOTE_WORKFLOW = ROOT / ".github/workflows/promote-release.yml"
RELEASE_WORKFLOW = ROOT / ".github/workflows/publish-release.yml"
VALIDATE_WORKFLOW = ROOT / ".github/workflows/validate.yml"
MACOS_WORKFLOW = ROOT / ".github/workflows/macos-opencode-compatibility.yml"
MACOS_HOMEBREW_WORKFLOW = (
    ROOT / ".github/workflows/macos-homebrew-compatibility.yml"
)


class PublishWorkflowContractTest(unittest.TestCase):
    def test_shell_run_blocks_never_expand_github_expressions_directly(self) -> None:
        """Keep attacker-controlled workflow values out of shell source text."""

        workflow_dir = ROOT / ".github/workflows"
        workflows = (*workflow_dir.glob("*.yml"), *workflow_dir.glob("*.yaml"))
        for workflow in sorted(workflows):
            lines = workflow.read_text(encoding="utf-8").splitlines()
            for index, line in enumerate(lines):
                stripped = line.lstrip()
                if not stripped.startswith("run:"):
                    continue
                indentation = len(line) - len(stripped)
                run_lines = [line]
                cursor = index + 1
                while cursor < len(lines):
                    candidate = lines[cursor]
                    candidate_indent = len(candidate) - len(candidate.lstrip())
                    if candidate.strip() and candidate_indent <= indentation:
                        break
                    run_lines.append(candidate)
                    cursor += 1
                self.assertNotIn(
                    "${{",
                    "\n".join(run_lines),
                    f"{workflow.name}:{index + 1} must pass expressions through env",
                )

    def test_copilot_compatibility_and_opencode_smokes_use_separate_runners(self) -> None:
        for workflow in (
            VALIDATE_WORKFLOW,
            WORKFLOW,
            PROMOTE_WORKFLOW,
            RELEASE_WORKFLOW,
        ):
            text = workflow.read_text(encoding="utf-8")
            parts = re.split(r"(?m)^  ([a-z0-9-]+):\n", text.split("jobs:\n", 1)[1])
            jobs = dict(zip(parts[1::2], parts[2::2]))
            self.assertIn("copilot-compatibility", jobs, workflow.name)
            for name, body in jobs.items():
                if "smoke_opencode" in body:
                    self.assertNotIn("@github/copilot", body, f"{workflow.name}:{name}")

    def test_opencode_smokes_recheck_absolute_verified_clients(self) -> None:
        for workflow in (
            VALIDATE_WORKFLOW,
            WORKFLOW,
            PROMOTE_WORKFLOW,
            RELEASE_WORKFLOW,
        ):
            text = workflow.read_text(encoding="utf-8")
            self.assertGreaterEqual(text.count('stat -c \'%a:%u\' "${OPENCODE_BIN}"'), 2)
            self.assertGreaterEqual(text.count('stat -c \'%a:%u\' "${CPLT_BIN}"'), 2)
            self.assertGreaterEqual(text.count('--opencode "${OPENCODE_BIN}"'), 2)
            self.assertIn('--cplt "${CPLT_BIN}"', text)
            self.assertIn(
                "PATH: ${{ runner.temp }}/opencode-bin:${{ runner.temp }}/cplt-bin:"
                "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                text,
            )
            self.assertNotIn('echo "${binary_dir}" >> "${GITHUB_PATH}"', text)

    def test_macos_gate_verifies_and_runs_pinned_native_clients(self) -> None:
        text = MACOS_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_call:", text)
        self.assertIn("runs-on: ${{ matrix.runner }}", text)
        self.assertIn("- macos-15", text)
        self.assertIn("- macos-15-intel", text)
        self.assertIn("timeout-minutes: 30", text)
        self.assertIn("persist-credentials: false", text)
        self.assertIn('ref: ${{ inputs.source_sha }}', text)
        self.assertNotIn("npm install", text)
        self.assertNotIn("@github/copilot", text)

        for archive, archive_digest, binary_digest in (
            (
                "opencode-darwin-arm64-1.18.20.tgz",
                "7e010126cc31f75380b44989cbb8934f6da262c69d0b29f8629eeb574f60fae7"
                "f9968c995e49f238b62620b6080ebbc43fa16b50bacf6160635a65aa22beae80",
                "9598c27bda0e2d88ce4db5f853e25504c20ac6152e10205785a1cf8f45559952",
            ),
            (
                "opencode-darwin-x64-1.18.20.tgz",
                "cbade5db7d9d2cf3175a66155aba13c5b77bc1f602b1178f05a5ec8bb9f77983"
                "cd7bb29ea3aacc97170db266c187173c3a609eaf4c83f4391a492e7230b83dc1",
                "96e4a9ecd931a059515fb2126cf59a4a3b56d9a66f9d4dbdf1361d1b4cd5ef60",
            ),
            (
                "cplt-aarch64-apple-darwin.tar.gz",
                "fb1fd69f5ff42deb1cf2e510d97a58ff5f7ddf913e1cd4f7533815a16588eeda",
                "423af2ce6166b0ddc1939d2e4d1340837daa23a29ccc58024ec0a849051becb2",
            ),
            (
                "cplt-x86_64-apple-darwin.tar.gz",
                "e60687724df8a2fdb6f99654cc80f1a0dccb215263c2d984c222ff99ce56f8ea",
                "36592c1b2bcfd7ab2d9083842b0aa7f51737cdf12ec1752d351bd9467dab5c02",
            ),
        ):
            with self.subTest(archive=archive):
                self.assertIn(archive, text)
                self.assertIn(archive_digest, text)
                self.assertIn(binary_digest, text)

        verifier = text.split(
            "Download and verify native Darwin clients before first execution",
            maxsplit=1,
        )[1].split("Run native Darwin discovery", maxsplit=1)[0]
        first_execution = verifier.index('"${verified_bin}/opencode" --version')
        for prerequisite in (
            "archive digest differs",
            "archive roster differs",
            "archive contains a link or special member",
            "executable digest differs",
            "os.O_EXCL",
            "os.fsync",
            "os.fchmod",
        ):
            self.assertLess(verifier.index(prerequisite), first_execution)

        self.assertIn("scripts/smoke_opencode.py", text)
        self.assertIn("scripts/smoke_opencode_runtime.py", text)
        self.assertIn('cmp -s "${bundle}" "${repeated}"', text)

    def test_macos_gate_reaches_the_installed_opencode_tui_through_cplt(self) -> None:
        workflow = MACOS_HOMEBREW_WORKFLOW.read_text(encoding="utf-8")
        gate = workflow.split('          tui_consumer="${qa_root}/tui-consumer"', 1)[
            1
        ].split("          cleanup", 1)[0]

        self.assertIn("scripts/smoke_grillmester_tui.py", gate)
        self.assertIn('--launcher "${prefix}/bin/grillmester"', gate)
        self.assertIn('--opencode "${opencode_binary}"', gate)
        self.assertIn('--opencode-version "${opencode_version}"', gate)
        self.assertIn('--cplt "${cplt_binary}"', gate)
        self.assertIn('--project-dir "${tui_consumer}"', gate)
        self.assertLess(
            workflow.index('brew install --formula "${formula_name}"'),
            workflow.index("\n          brew install opencode\n"),
        )
        self.assertLess(
            workflow.index("\n          brew install opencode\n"),
            workflow.index("scripts/smoke_grillmester_tui.py"),
        )

    def test_macos_gate_reaches_real_copilot_through_launcher_and_cplt_without_a_model_call(
        self,
    ) -> None:
        workflow = MACOS_HOMEBREW_WORKFLOW.read_text(encoding="utf-8")
        gate = workflow.split(
            "          brew install --cask copilot-cli", maxsplit=1
        )[1].split("          cleanup 0", maxsplit=1)[0]

        for marker in (
            'copilot_candidate="$(command -v copilot)"',
            'copilot_path_dir="${qa_root}/copilot-path"',
            'ln -s "${copilot_binary}" "${copilot_path_dir}/copilot"',
            'PATH="${copilot_client_path}" command -v opencode',
            'copilot_state="$(mktemp -d "${HOME}/.grillmester-copilot-qa.XXXXXX")"',
            'doctor --client copilot',
            '"${prefix}/bin/grillmester" --client copilot',
            '--agent grillmester --project-dir "${tui_consumer}"',
            '--yes --quiet --no-audit -- --help',
            "Usage: copilot ",
            'git -C "${tui_consumer}" status --porcelain',
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, gate)
        self.assertNotIn("--prompt", gate)
        self.assertNotIn(" -p ", gate)
        self.assertNotIn("opencode_candidate", gate)
        self.assertNotIn('dirname "${copilot_candidate}"', gate)
        self.assertLess(
            workflow.index("scripts/smoke_grillmester_tui.py"),
            workflow.index("brew install --cask copilot-cli"),
        )

    def test_native_macos_gate_exercises_focused_and_full_copilot_against_loopback_model(
        self,
    ) -> None:
        workflow = MACOS_WORKFLOW.read_text(encoding="utf-8")
        for marker in (
            "copilot-darwin-arm64.tar.gz",
            "2346bb691981c2997d65c1c5bc3cef1aeddc9edd37dcb2f970b911aa597e59f6",
            "fe779da7dd2342c1d23f0744873fa27d0251eaaee4dc6637fa53093639c0f3c9",
            "copilot-darwin-x64.tar.gz",
            "a1a9c1f25740f9a27b34eb14b70b5d3175794dc8bb410875531aa198b3abc18f",
            "15a2576566635fdd2dc0c84137ec7481e41a6982281391c62e58883aa5f39f41",
            'if [member.name for member in members] != ["copilot"]',
            "member.type not in {tarfile.REGTYPE, tarfile.AREGTYPE}",
            'echo "COPILOT_BIN=',
        ):
            with self.subTest(artifact_marker=marker):
                self.assertIn(marker, workflow)
        for marker in (
            'ripgrep_platform="aarch64-apple-darwin"',
            "24ad76777745fbff131c8fbc466742b011f925bfa4fffa2ded6def23b5b937be",
            "0e0cb83f5195f1f51bb8feef1fff5b0b171e82bd1db6bd35deee701a3e7102f8",
            'ripgrep_platform="x86_64-apple-darwin"',
            'ripgrep_archive_sha256="fc87e78f7cb3fea12d69072e7ef3b215"'
            '"09754717b746368fd40d88963630e2b3"',
            "923dcc25cab57d33f4e7dd0476d4b74a554401a38817e246a8d6101dcd51c50f",
            'ripgrep_root="ripgrep-14.1.1-${ripgrep_platform}"',
            "ripgrep archive roster differs",
            "ripgrep archive contains a link or special member",
            'echo "RIPGREP_BIN=',
        ):
            with self.subTest(ripgrep_marker=marker):
                self.assertIn(marker, workflow)
        matrix_gate = workflow.split(
            "      - name: Exercise every local-model context through the exact cplt clients",
            maxsplit=1,
        )[1].split(
            "      - name: Exercise focused and full Copilot through exact cplt and loopback BYOK",
            maxsplit=1,
        )[0]
        for marker in (
            '"${BUNDLE_ROOT}/scripts/smoke_grillmester_local.py"',
            "--require-binaries",
            '--cplt "${CPLT_BIN}"',
            '--opencode "${OPENCODE_BIN}"',
            '--copilot "${COPILOT_BIN}"',
            '--ripgrep "${RIPGREP_BIN}"',
            '"${RIPGREP_BINARY_SHA256}"',
        ):
            with self.subTest(matrix_marker=marker):
                self.assertIn(marker, matrix_gate)
        gate = workflow.split(
            "      - name: Exercise focused and full Copilot through exact cplt and loopback BYOK",
            maxsplit=1,
        )[1]

        for marker in (
            'HTTPServer(("127.0.0.1", 0), Handler)',
            '"/v1/models"',
            '"/v1/chat/completions"',
            'model = "ci-grillmester-local"',
            'answer = "GRILLMESTER_LOCAL_GATE_OK"',
            'AMBIENT_FULL_PLUGIN_MUST_NOT_LOAD',
            'local setup',
            '--context focused',
            'local doctor',
            'targets/copilot-cli-focused-v1',
            'local launch',
            "-p 'FOCUSED-GATE:",
            '--full',
            '"${BUNDLE_ROOT}/plugin"',
            "-p 'FULL-GATE:",
            'record.get("model") != "ci-grillmester-local"',
            'record.get("stream") is not True',
            'endswith("/chat/completions")',
            'overlay = "Resume with: grillmester local --full"',
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, gate)
        self.assertIn('provider_pid=$!', gate)
        self.assertIn('kill "${provider_pid}"', workflow)
        self.assertNotIn("api.github.com", gate)
        self.assertNotIn("githubcopilot.com", gate)
        self.assertLess(gate.index('local setup'), gate.index("-p 'FOCUSED-GATE:"))
        self.assertLess(gate.index("-p 'FOCUSED-GATE:"), gate.index("-p 'FULL-GATE:"))

    def test_macos_gate_is_bound_to_the_reviewed_darwin_artifact_lock(self) -> None:
        text = MACOS_WORKFLOW.read_text(encoding="utf-8")
        artifact_lock = json.loads(
            (ROOT / "policy/client-artifacts.json").read_text(encoding="utf-8")
        )
        selections = (
            ("opencode", "arm64", "default"),
            ("opencode", "x86_64", "default"),
            ("cplt", "arm64", "default"),
            ("cplt", "x86_64", "default"),
        )

        for client, architecture, variant in selections:
            matches = [
                artifact
                for artifact in artifact_lock[client]["artifacts"]
                if artifact["platform"] == "darwin"
                and artifact["architecture"] == architecture
                and artifact["variant"] == variant
            ]
            self.assertEqual(
                len(matches),
                1,
                f"{client} darwin/{architecture}/{variant}",
            )
            artifact = matches[0]
            archive_digest = artifact["archive"].get("sha512") or artifact[
                "archive"
            ]["sha256"]
            for value in (
                artifact["url"],
                str(artifact["archive"]["size"]),
                archive_digest,
                str(artifact["executable"]["size"]),
                artifact["executable"]["sha256"],
            ):
                with self.subTest(
                    client=client,
                    architecture=architecture,
                    variant=variant,
                    value=value,
                ):
                    self.assertIn(value, text)

    def test_macos_gate_installs_and_tests_the_generated_homebrew_formula(self) -> None:
        text = MACOS_HOMEBREW_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("runs-on: ${{ matrix.runner }}", text)
        self.assertIn("- macos-15", text)
        self.assertIn("- macos-15-intel", text)
        self.assertIn("persist-credentials: false", text)
        self.assertIn("contents: read", text)
        gate = text.split(
            "Install and test the generated Homebrew formula", maxsplit=1
        )[1]
        self.assertEqual(2, gate.count("scripts/build_opencode_bundle.py"))
        self.assertNotIn("brew install --overwrite", gate)
        self.assertNotIn("brew install --ignore-dependencies", gate)

        for marker in (
            'cmp -s "${bundle}" "${repeated}"',
            "prepare_hosted_intel_python_links",
            "restore_hosted_intel_python_links",
            'readlink "${target}"',
            'brew uninstall --formula python@3.13',
            'mv "${target}" "${backup}"',
            'mv "${backup}" "${target}"',
            "scripts/generate_homebrew_formula.py",
            'ruby -c "${formula}"',
            'brew tap-new --no-git "${tap_name}"',
            "brew tap navikt/tap",
            'brew style "${formula_name}"',
            'brew audit --strict "${formula_name}"',
            'brew install --formula "${formula_name}"',
            'brew test --verbose "${formula_name}"',
            "Grillmester unexpectedly found OpenCode outside the caller PATH.",
            "OpenCode was not found on PATH; install it with: brew install opencode",
            "brew install opencode",
            "brew install --cask copilot-cli",
            "doctor --client opencode",
            "doctor --client copilot",
            'cplt_candidate="$(brew --prefix navikt/tap/cplt)/bin/cplt"',
            'opencode_candidate="$(brew --prefix opencode)/bin/opencode"',
            '[[ ! -e "${prefix}/libexec/clients"',
            '--opencode-version "${opencode_version}"',
            "anomalyco/opencode",
            "navikt/cplt",
            'brew uninstall --formula "${formula_name}"',
            "brew uninstall --formula opencode",
            "brew uninstall --cask copilot-cli",
            "brew uninstall --formula navikt/tap/cplt",
            "brew untap navikt/tap",
            '[[ ! -e "${linked_launcher}" && ! -L "${linked_launcher}" ]]',
            '[[ ! -e "${prefix}" && ! -L "${prefix}" ]]',
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, gate)

        for obsolete in (
            "libexec/clients/cplt",
            "libexec/clients/opencode",
            "cplt_binary_sha256",
            "opencode_binary_sha256",
        ):
            with self.subTest(obsolete=obsolete):
                self.assertNotIn(obsolete, gate)

    def test_release_macos_gate_tests_the_exact_sealed_formula(self) -> None:
        macos = MACOS_HOMEBREW_WORKFLOW.read_text(encoding="utf-8")
        install = macos.split(
            "Install and test the generated Homebrew formula", maxsplit=1
        )[1]

        for marker in (
            'encoded = os.environ["SEALED_FORMULA_BASE64"]',
            "base64.b64decode(encoded, validate=True)",
            "hashlib.sha256(content).hexdigest() != expected_digest",
            'cp "${sealed_formula}" "${formula}"',
        ):
            self.assertIn(marker, install)
        self.assertIn('cmp -s "${expected_formula}" "${formula}"', install)
        self.assertLess(
            install.index('cmp -s "${expected_formula}" "${formula}"'),
            install.index('brew install --formula "${formula_name}"'),
        )

        release = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        verify_job = release.split(
            "\n  verify-release-assets:\n", maxsplit=1
        )[1].split("\n  release:\n", maxsplit=1)[0]
        export = verify_job.split(
            "Export independently verified formula for macOS", maxsplit=1
        )[1].split("Independently enforce stable rights approval", maxsplit=1)[0]
        for marker in (
            'Path(os.environ["RUNNER_TEMP"]) / os.environ["FORMULA_NAME"]',
            'hashlib.sha256(content).hexdigest() != os.environ["FORMULA_SHA256"]',
            "base64.b64encode(content).decode(\"ascii\")",
            'output.write(f"formula_base64={encoded}\\n")',
        ):
            self.assertIn(marker, export)
        self.assertLess(
            verify_job.index("Independently bind formula with trusted release tooling"),
            verify_job.index("Export independently verified formula for macOS"),
        )

    def test_macos_gate_proves_strict_native_copilot_domain_composition_without_auth(self) -> None:
        text = MACOS_WORKFLOW.read_text(encoding="utf-8")
        gate = text.split(
            "Prove strict native OpenCode Copilot-provider network policy without auth",
            maxsplit=1,
        )[1].split("Run native Darwin discovery", maxsplit=1)[0]

        self.assertIn("--agent opencode", gate)
        self.assertIn("--preset strict", gate)
        self.assertIn("--allowed-domains", gate)
        self.assertIn("--no-connect", gate)
        self.assertNotIn("--allow-all-domains", gate)
        self.assertNotIn("/connect", gate)
        for domain in (
            "githubcopilot.com",
            "api.github.com",
            "github.com",
            "copilot-proxy.githubusercontent.com",
            "actions.githubusercontent.com",
            "default.exp2.cds.s9ch.io",
        ):
            with self.subTest(domain=domain):
                self.assertIn(domain, gate)
        self.assertIn('"github.com:443" "allowed"', gate)
        self.assertIn('"api.githubcopilot.com:443" "allowed"', gate)
        self.assertIn('"exfiltration.invalid:443" "blocked"', gate)
        self.assertIn('.items[0].decision == $decision', gate)

    def test_macos_gate_proves_cplt_policy_socket_pin_and_manager_launch(self) -> None:
        text = MACOS_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('CPLT_CONFIG="${policy}/cplt-config.toml"', text)
        self.assertIn('"${policy_command[@]}" check --json', text)
        self.assertIn('.platform == "macos (Seatbelt)"', text)
        self.assertIn('.items | length) == 7 and .verified == 4', text)
        self.assertIn('.target == "opencode.ai:443"', text)
        self.assertIn('.expected == "allowed" and .decision == "blocked"', text)
        self.assertIn('.target == "169.254.169.254:443"', text)
        self.assertIn('.expected == "blocked" and .decision == "blocked"', text)
        self.assertIn("check --json net", text)
        self.assertIn('"127.0.0.1:${listener_port}" --no-connect', text)
        self.assertIn('check --json net opencode.ai:443', text)
        self.assertIn('/usr/bin/nc -z -G 2 127.0.0.1 "${listener_port}"', text)
        self.assertIn('/usr/bin/nc -z -G 2 "${runner_ip}" "${listener_port}"', text)
        self.assertIn('remote_same_port="198.51.100.1:${listener_port}"', text)
        self.assertIn('.items[0].decision == "blocked"', text)
        self.assertIn('manage_opencode.py" install', text)
        self.assertIn('--source "${BUNDLE_ROOT}"', text)
        self.assertIn('manage_opencode.py" launch', text)
        self.assertIn('--profile local-only --local-port "${LOCAL_PROVIDER_PORT}"', text)
        self.assertIn("listener_ready=false", text)
        self.assertIn("for _attempt in {1..100}", text)
        self.assertIn('[[ "${listener_ready}" == true ]]', text)
        self.assertIn('npm: "@ai-sdk/openai-compatible"', text)
        self.assertIn('limit: {context: 32768, output: 8192}', text)
        self.assertIn('--provider-id ci-local', text)
        self.assertIn(
            '--provider-base-url "ci-local=http://127.0.0.1:${LOCAL_PROVIDER_PORT}/v1"',
            text,
        )
        self.assertIn('--provider-model ci-local/ci-model', text)
        self.assertIn(
            '--opencode "${OPENCODE_BIN}" --cplt "${CPLT_BIN}" --',
            text,
        )
        self.assertIn("models ci-local --verbose", text)
        self.assertIn("grep -F 'ci-local/ci-model'", text)
        self.assertIn("grep -F '\"context\": 32768'", text)
        self.assertIn("grep -F '\"output\": 8192'", text)

    def test_all_workflow_checkouts_disable_persisted_credentials(self) -> None:
        for workflow in (
            VALIDATE_WORKFLOW,
            WORKFLOW,
            PROMOTE_WORKFLOW,
            RELEASE_WORKFLOW,
            MACOS_WORKFLOW,
        ):
            text = workflow.read_text(encoding="utf-8")
            checkout_blocks = text.split("uses: actions/checkout@")[1:]
            self.assertTrue(checkout_blocks, workflow.name)
            for checkout in checkout_blocks:
                block = checkout.split("\n      - name:", maxsplit=1)[0]
                self.assertIn("persist-credentials: false", block, workflow.name)

    def test_workflow_downloads_ignore_ambient_curl_configuration(self) -> None:
        for workflow in (
            VALIDATE_WORKFLOW,
            WORKFLOW,
            PROMOTE_WORKFLOW,
            RELEASE_WORKFLOW,
            MACOS_WORKFLOW,
        ):
            curl_lines = [
                line for line in workflow.read_text(encoding="utf-8").splitlines()
                if "curl " in line
            ]
            self.assertTrue(curl_lines, workflow.name)
            for line in curl_lines:
                self.assertIn("curl --config /dev/null", line, workflow.name)

    def test_every_copilot_install_pins_node_first_in_the_same_job(self) -> None:
        for workflow in (
            VALIDATE_WORKFLOW,
            WORKFLOW,
            PROMOTE_WORKFLOW,
            RELEASE_WORKFLOW,
        ):
            text = workflow.read_text(encoding="utf-8")
            parts = re.split(
                r"(?m)^  ([a-z0-9-]+):\n",
                text.split("jobs:\n", maxsplit=1)[1],
            )
            jobs = dict(zip(parts[1::2], parts[2::2]))
            setup = "actions/setup-node@820762786026740c76f36085b0efc47a31fe5020"
            install = "npm install --global @github/copilot@1.0.79"
            install_jobs = {name: body for name, body in jobs.items() if install in body}
            self.assertTrue(install_jobs, workflow.name)
            for name, body in install_jobs.items():
                label = f"{workflow.name}:{name}"
                self.assertEqual(1, body.count(install), label)
                self.assertIn("node-version: 22", body, label)
                self.assertLess(body.index(setup), body.index(install), label)

    def test_every_gate_calls_macos_compatibility_for_the_exact_source(self) -> None:
        expected_sources = {
            VALIDATE_WORKFLOW: "${{ github.sha }}",
            WORKFLOW: "${{ inputs.source_sha }}",
            PROMOTE_WORKFLOW: "${{ needs.validate.outputs.source-sha }}",
            RELEASE_WORKFLOW: "${{ needs.validate.outputs.source-sha }}",
        }
        for workflow, source in expected_sources.items():
            text = workflow.read_text(encoding="utf-8")
            job = text.split("\n  macos-live-compatibility:\n", maxsplit=1)[1]
            job = re.split(r"(?m)^  [a-z0-9-]+:\n", job, maxsplit=1)[0]
            self.assertIn(
                "uses: ./.github/workflows/macos-opencode-compatibility.yml",
                job,
                workflow.name,
            )
            self.assertIn(f"source_sha: {source}", job, workflow.name)
            self.assertIn("contents: read", job, workflow.name)
            self.assertNotIn("actions: read", job, workflow.name)

    def test_homebrew_gate_is_structurally_unreachable_from_manual_inputs(self) -> None:
        core = MACOS_WORKFLOW.read_text(encoding="utf-8")
        homebrew = MACOS_HOMEBREW_WORKFLOW.read_text(encoding="utf-8")

        self.assertNotIn("Install and test the generated Homebrew formula", core)
        self.assertNotIn("brew install", core)
        self.assertIn("Install and test the generated Homebrew formula", homebrew)
        self.assertNotIn("workflow_dispatch", homebrew)
        self.assertNotIn("actions: read", homebrew)
        self.assertNotIn("github.token", homebrew)
        self.assertNotIn("/actions/artifacts/", homebrew)

        reusable = "uses: ./.github/workflows/macos-homebrew-compatibility.yml"
        for workflow in (WORKFLOW, PROMOTE_WORKFLOW):
            self.assertNotIn(reusable, workflow.read_text(encoding="utf-8"))

        expected_sources = {
            VALIDATE_WORKFLOW: "${{ github.sha }}",
            RELEASE_WORKFLOW: "${{ needs.validate.outputs.source-sha }}",
        }
        for workflow, source in expected_sources.items():
            text = workflow.read_text(encoding="utf-8")
            job = text.split("\n  macos-homebrew-compatibility:\n", maxsplit=1)[1]
            job = re.split(r"(?m)^  [a-z0-9-]+:\n", job, maxsplit=1)[0]
            self.assertIn(reusable, job, workflow.name)
            self.assertIn(f"source_sha: {source}", job, workflow.name)
            self.assertIn("contents: read", job, workflow.name)
            self.assertNotIn("actions: read", job, workflow.name)

        release = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        verify_job = release.split(
            "\n  verify-release-assets:\n", maxsplit=1
        )[1].split("\n  release:\n", maxsplit=1)[0]
        release_job = release.split(
            "\n  macos-homebrew-compatibility:\n", maxsplit=1
        )[1].split("\n  macos-live-compatibility:\n", maxsplit=1)[0]
        self.assertIn("formula-base64:", verify_job)
        self.assertIn("needs.verify-release-assets.outputs.formula-base64", release_job)
        self.assertNotIn("release_artifact_", release_job)

    def test_every_release_gate_uses_the_pinned_native_opencode_smoke(self) -> None:
        workflows = {
            "validate": VALIDATE_WORKFLOW.read_text(encoding="utf-8"),
            "marketplace": WORKFLOW.read_text(encoding="utf-8"),
            "manual release validation": PROMOTE_WORKFLOW.read_text(encoding="utf-8"),
            "release publication": RELEASE_WORKFLOW.read_text(encoding="utf-8"),
        }
        for label, text in workflows.items():
            with self.subTest(workflow=label):
                self.assertNotIn("npm install --global opencode-ai@1.18.20", text)
                self.assertNotIn("npm install -g opencode-ai@1.18.20", text)
                self.assertIn(
                    "opencode-linux-x64/-/opencode-linux-x64-1.18.20.tgz",
                    text,
                )
                self.assertIn(
                    "1fe5e153b35b7d306df98135cdab1876e9637ef79941b6adc3bda00d485629f9"
                    "c4f3781df4a67cbb96e209fed364472c8bd40979b1606b6513ade6ec8afcd0ba",
                    text,
                )
                self.assertIn(
                    "5dce99ea079d925736e332b20f5bf869fe9a1fa67dc0a09027156b0ed8e41b16",
                    text,
                )
                self.assertIn("sha512sum --check --strict", text)
                self.assertIn('"package/bin/opencode"', text)
                self.assertIn("smoke_opencode.py", text)
                self.assertIn("smoke_opencode_runtime.py", text)
                self.assertIn("--require-binary", text)
                self.assertIn(
                    '[[ "${#cplt_entries[@]}" == "1" && '
                    '"${cplt_entries[0]}" == "cplt" ]]',
                    text,
                )
                self.assertIn("--no-same-owner --no-same-permissions -- cplt", text)
                self.assertIn("--max-filesize 10000000", text)
                self.assertIn(
                    "115fff00248f0c170388e11f2a05cc9914f5ba589f2ca87817ed96de2c6eedb5",
                    text,
                )

        self.assertIn(
            'python3 "${SOURCE_ROOT}/scripts/smoke_opencode.py"',
            workflows["marketplace"],
        )
        self.assertIn(
            'python3 "${SOURCE_ROOT}/scripts/smoke_opencode_runtime.py"',
            workflows["marketplace"],
        )
        for label in ("manual release validation", "release publication"):
            self.assertIn(
                'python3 "${SOURCE_ROOT}/scripts/smoke_opencode.py"',
                workflows[label],
            )
            self.assertIn(
                'python3 "${SOURCE_ROOT}/scripts/smoke_opencode_runtime.py"',
                workflows[label],
            )

    def test_write_credentials_exist_only_in_final_publish_step(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("persist-credentials: false", text)
        self.assertEqual(1, text.count("GH_TOKEN: ${{ github.token }}"))
        self.assertEqual(1, text.count("contents: write"))
        self.assertLess(
            text.index("Publish catalog-only commit atomically"),
            text.index("GH_TOKEN: ${{ github.token }}"),
        )
        write_job = text.split("\n  publish:\n", maxsplit=1)[1].split(
            "\n  remote-smoke:\n", maxsplit=1
        )[0]
        self.assertIn("contents: write", write_job)
        self.assertEqual(1, write_job.count("      - name:"))
        self.assertNotIn("uses:", write_job)
        self.assertNotIn("python3", write_job)
        self.assertNotIn("--force-with-lease", write_job)
        self.assertLess(
            text.index("Seal catalog before executing source tooling"),
            text.index("Install pinned GitHub Copilot CLI"),
        )

    def test_publisher_rejects_marketplace_version_reuse(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("Refusing to reuse marketplace version", text)
        self.assertIn("Refusing to reuse previously published marketplace version", text)
        self.assertIn("git rev-list --skip=1", text)
        self.assertIn('git ls-remote --heads origin "refs/heads/${MARKETPLACE_BRANCH}"', text)
        self.assertIn("git push origin --atomic", text)

    def test_marketplace_write_job_is_protected_and_needs_every_gate(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        write_job = text.split("\n  publish:\n", maxsplit=1)[1].split(
            "\n  remote-smoke:\n", maxsplit=1
        )[0]
        self.assertIn(
            "needs:\n"
            "      - validate\n"
            "      - copilot-compatibility\n"
            "      - macos-live-compatibility",
            write_job,
        )
        self.assertIn("environment: grillmester-release", write_job)
        self.assertIn("contents: write", write_job)

    def test_marketplace_version_gate_implements_semver_precedence(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        start = text.index("          compare_numeric_identifier() {")
        end = text.index('          [[ "${SOURCE_SHA}" =~', start)
        functions = textwrap.dedent(text[start:end])
        checks = r'''
        expect_compare() {
          semver_compare "$1" "$2"
          [[ "${SEMVER_COMPARE}" == "$3" ]]
        }
        expect_compare 1.0.0-rc.10 1.0.0-rc.2 1
        expect_compare 1.0.0 1.0.0-rc.99 1
        expect_compare 1.0.1 1.0.0 1
        expect_compare 2.0.0 10.0.0 -1
        expect_compare 1.0.0-alpha.1 1.0.0-alpha.beta -1
        expect_compare 999999999999999999.0.0 10.0.0 1
        if semver_compare 1.0.0-rc.01 1.0.0-rc.1; then exit 20; fi
        if semver_compare 1.0.0+build 1.0.0; then exit 21; fi
        '''
        result = subprocess.run(
            ["bash", "-s"],
            input="set -euo pipefail\nexport LC_ALL=C\n" + functions + checks,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            'semver_compare "${CATALOG_VERSION}" "${CATALOG_VERSION}"', text
        )
        self.assertIn("Refusing marketplace downgrade", text)

    def test_idempotent_rerun_requires_tip_bytes_to_match_sealed_catalog(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        write_job = text.split("\n  publish:\n", maxsplit=1)[1].split(
            "\n  remote-smoke:\n", maxsplit=1
        )[0]
        source_match = '[[ "${SOURCE_SHA}" == "${previous_source_sha}" ]]'
        digest = (
            'previous_catalog_sha256="$(git show "${base_sha}:${catalog}" '
            '| sha256sum | cut -d\' \' -f1)"'
        )
        identity_match = (
            '[[ "${CATALOG_SHA256}" == "${previous_catalog_sha256}" ]]'
        )
        success = 'echo "Marketplace already publishes ${current_version} at ${SOURCE_SHA}."'
        self.assertIn(digest, write_job)
        self.assertIn(identity_match, write_job)
        self.assertIn(
            "Refusing idempotent marketplace rerun: existing catalog bytes do not match the sealed catalog.",
            write_job,
        )
        self.assertLess(write_job.index(source_match), write_job.index(digest))
        self.assertLess(write_job.index(digest), write_job.index(identity_match))
        self.assertLess(write_job.index(identity_match), write_job.index(success))

    def test_marketplace_promotion_is_explicit_and_not_push_triggered(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        trigger = text.split("\nconcurrency:", maxsplit=1)[0]
        self.assertIn("workflow_dispatch:", trigger)
        self.assertIn("channel:", trigger)
        self.assertIn("source_sha:", trigger)
        self.assertIn("rc_tag:", trigger)
        self.assertIn("required: true", trigger)
        self.assertIn("type: string", trigger)
        self.assertNotIn("push:", trigger)
        self.assertNotIn("paths:", trigger)

    def test_stable_marketplace_write_is_gated_by_rc_payload_rights_and_assets(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        validate_job = text.split("\n  validate:\n", maxsplit=1)[1].split(
            "\n  copilot-compatibility:\n", maxsplit=1
        )[0]
        publish_job = text.split("\n  publish:\n", maxsplit=1)[1].split(
            "\n  remote-smoke:\n", maxsplit=1
        )[0]
        for marker in (
            'CHANNEL: ${{ inputs.channel }}',
            'RC_TAG: ${{ inputs.rc_tag }}',
            'validate-source-promotion',
            '--rc-source-repo "${rc_source_repo}"',
            'policy/stable-rights-approval.json',
            'git cat-file -t "refs/tags/${RC_TAG}"',
            '(.assets | length) == 3',
            "'.immutable'",
            'python3 "${rc_source_repo}/scripts/build_opencode_bundle.py"',
            'cmp -s "${rc_rebuilt_bundle}" "${rc_published_bundle}"',
            'sha256sum --check --strict',
            '.label == "Homebrew formula"',
            'scripts/generate_homebrew_formula.py',
            'cmp -s "${rc_expected_formula}" "${rc_published_formula}"',
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, validate_job)
        self.assertLess(
            validate_job.index("validate-source-promotion"),
            validate_job.index(
                'python3 "${rc_source_repo}/scripts/build_opencode_bundle.py"'
            ),
        )
        self.assertNotIn("validate-source-promotion", publish_job)

    def test_promotion_requires_current_main_and_exact_reachable_source_sha(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('SOURCE_SHA: ${{ inputs.source_sha }}', text)
        self.assertIn('DISPATCH_REF: ${{ github.ref }}', text)
        self.assertIn('DISPATCH_SHA: ${{ github.sha }}', text)
        self.assertIn('[[ "${DISPATCH_REF}" == "refs/heads/main" ]]', text)
        self.assertIn('[[ "${SOURCE_SHA}" =~ ^[0-9a-f]{40}$ ]]', text)
        self.assertIn('[[ "${DISPATCH_SHA}" == "$(git rev-parse refs/remotes/origin/main)" ]]', text)
        self.assertIn('git cat-file -e "${SOURCE_SHA}^{commit}"', text)
        self.assertIn('git merge-base --is-ancestor \\\n            "${SOURCE_SHA}" refs/remotes/origin/main', text)
        self.assertIn('WORKFLOW_SHA: ${{ github.sha }}', text)
        self.assertNotIn("needs.validate.outputs.source-sha", text)
        self.assertNotIn("needs.validate.outputs.workflow-sha", text)
        self.assertNotIn("steps.source.outputs.sha", text)
        self.assertNotIn("steps.source.outputs.workflow_sha", text)
        self.assertIn(
            'The selected workflow SHA is no longer current origin/main.', text
        )

    def test_catalog_publisher_revalidates_exact_one_plugin_roster(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        write_job = text.split("\n  publish:\n", maxsplit=1)[1]
        self.assertIn("(.plugins | length) == 1", write_job)
        self.assertIn(
            '[.plugins[].name] == ["grillmester"]',
            write_job,
        )
        self.assertIn('path: "plugin"', write_job)
        self.assertNotIn('path: "plugin-nav"', write_job)
        self.assertIn('[.plugins[].version] == [$version]', write_job)
        self.assertEqual(2, write_job.count("sha: $source_sha"))
        self.assertIn(
            'git show "${SOURCE_SHA}:package-manifest.json"', write_job
        )
        self.assertIn(
            'git show "${SOURCE_SHA}:plugin/plugin.json"', write_job
        )
        self.assertEqual(
            2,
            text.count('entry="$(git ls-tree "${SOURCE_SHA}" -- "${source_file}")"'),
        )
        self.assertIn(
            '[[ -f "${source_root}/${source_file}" && ! -L "${source_root}/${source_file}" ]]',
            text,
        )
        self.assertEqual(
            2,
            text.count('.repository == "https://github.com/navikt/grillmester"'),
        )
        self.assertEqual(2, text.count('.author == {name: $owner}'))
        self.assertEqual(2, text.count('.license == "MIT"'))
        self.assertIn('cmp -s "${regenerated_catalog}" "${catalog}"', write_job)

    def test_validation_regenerates_and_seals_catalog_from_exact_source_before_write(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('git worktree add --detach "${source_root}" "${SOURCE_SHA}"', text)
        self.assertIn(
            'python3 "${source_root}/scripts/generate_marketplace.py" \\\n            --mode release --sha "${SOURCE_SHA}"',
            text,
        )
        self.assertIn('--mode release --sha "${SOURCE_SHA}" --check', text)
        self.assertIn('python3 "${source_root}/scripts/validate.py"', text)
        self.assertLess(
            text.index("Seal catalog before executing source tooling"),
            text.index("Validate exact source against sealed catalog"),
        )
        self.assertLess(
            text.index('.author == {name: $owner}'),
            text.index("Seal catalog before executing source tooling"),
        )
        self.assertLess(
            text.index("Validate exact source against sealed catalog"),
            text.index("Publish catalog-only commit atomically"),
        )

    def test_manual_validator_is_read_only_and_smokes_exact_local_payload(self) -> None:
        text = PROMOTE_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("catalog_sha:", text)
        self.assertIn("refs/remotes/origin/marketplace", text)
        self.assertIn("refs/remotes/origin/main", text)
        self.assertNotIn("--remote-marketplace-ref", text)
        self.assertIn('--source-root "${GITHUB_WORKSPACE}"', text)
        self.assertNotIn("--source-plugin", text)
        self.assertIn(
            '[.plugins[].name] == ["grillmester"]', text
        )
        self.assertNotIn('path: "plugin-nav"', text)
        self.assertIn("api.github.com/repos/${GITHUB_REPOSITORY}/releases/tags/${RC_TAG}", text)
        self.assertIn('[[ "$(jq -r \'.immutable\' <<<"${rc_release}")" == "true" ]]', text)
        self.assertIn("contents: read", text)
        self.assertNotIn("contents: write", text)
        self.assertNotIn("GH_TOKEN", text)
        self.assertNotIn("release create", text)

    def test_promoter_and_publisher_share_concurrency_lock(self) -> None:
        publish = WORKFLOW.read_text(encoding="utf-8")
        promote = PROMOTE_WORKFLOW.read_text(encoding="utf-8")
        release = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        lock = "group: publish-grillmester-marketplace"
        self.assertIn(lock, publish)
        self.assertIn(lock, promote)
        self.assertIn(lock, release)

    def test_floating_marketplace_remote_smoke_is_read_only(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        publish = text.split("\n  publish:\n", maxsplit=1)[1].split(
            "\n  remote-smoke:\n", maxsplit=1
        )[0]
        remote_smoke = text.split("\n  remote-smoke:\n", maxsplit=1)[1]
        for job in (publish, remote_smoke):
            self.assertIn('SOURCE_SHA: ${{ inputs.source_sha }}', job)
            self.assertIn('WORKFLOW_SHA: ${{ github.sha }}', job)
            self.assertNotIn("needs.validate.outputs.source-sha", job)
            self.assertNotIn("needs.validate.outputs.workflow-sha", job)
        self.assertIn("- publish", remote_smoke)
        self.assertIn("contents: read", remote_smoke)
        self.assertNotIn("contents: write", remote_smoke)
        self.assertNotIn("GH_TOKEN", remote_smoke)
        self.assertIn('ref: ${{ github.sha }}', remote_smoke)
        self.assertIn("refs/remotes/origin/marketplace", remote_smoke)
        self.assertIn('git worktree add --detach \\\n            "${marketplace_root}" refs/remotes/origin/marketplace', remote_smoke)
        self.assertIn(
            '--remote-marketplace-ref "navikt/grillmester#marketplace"', remote_smoke
        )
        self.assertIn("--allow-floating-marketplace", remote_smoke)

    def test_promoter_has_a_real_failing_main_guard(self) -> None:
        text = PROMOTE_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('DISPATCH_REF: ${{ github.ref }}', text)
        self.assertIn('[[ "${DISPATCH_REF}" == "refs/heads/main" ]]', text)
        self.assertNotIn("if: github.ref == 'refs/heads/main'", text)

    def test_release_requires_reviewed_request_on_main(self) -> None:
        text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('branches:\n      - main', text)
        self.assertIn('- ".github/release-request.json"', text)
        self.assertNotIn("workflow_dispatch", text)
        self.assertIn(
            '(keys | sort) == ["catalogSha", "channel", "rcTag", "requestId", "schemaVersion"]',
            text,
        )
        self.assertIn('git show "${MAIN_SHA}:.github/release-request.json"', text)
        self.assertIn("request_id=${request_id}", text)
        self.assertIn('BEFORE_SHA: ${{ github.event.before }}', text)
        self.assertEqual(
            3,
            text.count('git diff --name-only "${BEFORE_SHA}" "${MAIN_SHA}"'),
        )
        self.assertEqual(
            3,
            text.count('git merge-base --is-ancestor "${BEFORE_SHA}" "${MAIN_SHA}"'),
        )

    def test_release_credentials_are_confined_to_two_protected_steps(self) -> None:
        text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        self.assertEqual(1, text.count("GH_TOKEN: ${{ github.token }}"))
        self.assertEqual(
            1,
            text.count(
                "IMMUTABLE_RELEASES_ADMIN_READ_TOKEN: "
                "${{ secrets.IMMUTABLE_RELEASES_ADMIN_READ_TOKEN }}"
            ),
        )
        self.assertLess(
            text.index("Require immutable GitHub Releases before publication"),
            text.index("Publish exact reviewed release idempotently"),
        )
        self.assertLess(
            text.index("Publish exact reviewed release idempotently"),
            text.index("GH_TOKEN: ${{ github.token }}"),
        )
        write_job = text.split("\n  release:\n", maxsplit=1)[1].split(
            "\n  remote-smoke:\n", maxsplit=1
        )[0]
        verify_job = text.split("\n  verify-release-assets:\n", maxsplit=1)[1].split(
            "\n  release:\n", maxsplit=1
        )[0]
        self.assertIn("environment: grillmester-release", write_job)
        self.assertIn("actions: read", write_job)
        self.assertIn("contents: write", write_job)
        self.assertEqual(2, write_job.count("      - name:"))
        self.assertNotIn("uses:", write_job)
        self.assertNotIn("python3", write_job)
        immutable_step, publish_step = write_job.split(
            "      - name: Publish exact reviewed release idempotently",
            maxsplit=1,
        )
        self.assertIn(
            "${{ secrets.IMMUTABLE_RELEASES_ADMIN_READ_TOKEN }}",
            immutable_step,
        )
        self.assertNotIn("${{ github.token }}", immutable_step)
        self.assertNotIn("IMMUTABLE_RELEASES_ADMIN_READ_TOKEN", publish_step)
        self.assertIn("GH_TOKEN: ${{ github.token }}", publish_step)
        self.assertIn(
            '"https://api.github.com/repos/${REPOSITORY}/immutable-releases"',
            immutable_step,
        )
        self.assertIn("X-GitHub-Api-Version: 2026-03-10", immutable_step)
        self.assertIn('.enabled == true', immutable_step)
        for mutation in ("-X POST", "-X PATCH", "-X PUT", "-X DELETE", "git push", "gh "):
            self.assertNotIn(mutation, immutable_step)
        self.assertIn("origin/main", write_job)
        self.assertIn("origin/marketplace", write_job)
        self.assertIn("--verify-tag", write_job)
        self.assertIn('cmp -s "${regenerated_catalog}" "${catalog_file}"', write_job)
        self.assertIn("jq -cS 'del(.version)'", write_job)
        self.assertIn(
            'cmp -s "${normalized_standard_manifest}" "${rc_standard_manifest_file}"',
            write_job,
        )
        self.assertIn(
            'cmp -s "${package_manifest_file}" "${rc_package_manifest_file}"',
            write_job,
        )
        self.assertIn(
            'git cat-file -e "${SOURCE_SHA}:targets/opencode-v1/opencode.json"',
            write_job,
        )
        for path in (
            "targets/opencode-v1",
            "targets/opencode-v1-focused",
            "profiles/opencode",
            "policy/focused-context-v1.json",
            "scripts/generate_context_projections.py",
            "scripts/grillmester_local.py",
            "scripts/smoke_grillmester_local.py",
        ):
            self.assertIn(path, write_job)
        self.assertIn("targets/copilot-cli-focused-v1", verify_job)
        self.assertIn("stable_focused_digest", verify_job)
        self.assertIn(
            'cmp -s "${regenerated_rc_catalog}" "${rc_catalog_file}"', write_job
        )
        self.assertIn("-- plugin ':(exclude)plugin/plugin.json'", write_job)
        self.assertNotIn("plugin-nav", write_job)
        self.assertIn('git ls-tree -r "${RC_CATALOG_SHA}"', write_job)
        self.assertIn("'.tag_name'", write_job)
        self.assertIn('git cat-file -t "${object}"', write_job)
        self.assertIn("Refusing non-annotated release tag", write_job)
        self.assertNotIn("git tag -f", write_job)
        self.assertNotIn("git push --force", write_job)
        self.assertNotIn("git push -f", write_job)
        self.assertNotIn("--force-with-lease", write_job)

    def test_release_write_waits_for_every_compatibility_and_asset_gate(self) -> None:
        text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        write_job = text.split("\n  release:\n", maxsplit=1)[1].split(
            "\n  remote-smoke:\n", maxsplit=1
        )[0]
        self.assertIn(
            "needs:\n"
            "      - validate\n"
            "      - copilot-compatibility\n"
            "      - macos-homebrew-compatibility\n"
            "      - macos-live-compatibility\n"
            "      - verify-release-assets",
            write_job,
        )

    def test_candidate_code_runs_without_repository_or_admin_tokens(self) -> None:
        release = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        release_candidate = release.split("\n  validate:\n", maxsplit=1)[1].split(
            "\n  copilot-compatibility:\n", maxsplit=1
        )[0]
        self.assertNotIn("github.token", release_candidate)
        self.assertNotIn("IMMUTABLE_RELEASES_ADMIN_READ_TOKEN", release_candidate)

        promote = PROMOTE_WORKFLOW.read_text(encoding="utf-8")
        self.assertNotIn("github.token", promote, PROMOTE_WORKFLOW.name)
        self.assertNotIn(
            "IMMUTABLE_RELEASES_ADMIN_READ_TOKEN", promote, PROMOTE_WORKFLOW.name
        )

        macos = MACOS_WORKFLOW.read_text(encoding="utf-8")
        self.assertNotIn("IMMUTABLE_RELEASES_ADMIN_READ_TOKEN", macos)
        self.assertNotIn("github.token", macos)
        self.assertNotIn("/actions/artifacts/", macos)
        homebrew = MACOS_HOMEBREW_WORKFLOW.read_text(encoding="utf-8")
        self.assertNotIn("IMMUTABLE_RELEASES_ADMIN_READ_TOKEN", homebrew)
        self.assertNotIn("github.token", homebrew)
        self.assertNotIn("/actions/artifacts/", homebrew)

    def test_published_release_must_read_back_as_immutable(self) -> None:
        text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        write_job = text.split("\n  release:\n", maxsplit=1)[1].split(
            "\n  remote-smoke:\n", maxsplit=1
        )[0]
        function = write_job.split("          verify_release_metadata() {", maxsplit=1)[1]
        function = function.split("          verify_release_asset_roster()", maxsplit=1)[0]
        self.assertIn('if [[ "${expected_draft}" == "false" ]]', function)
        self.assertIn('jq -r \'.immutable\'', function)
        self.assertLess(
            write_job.index('release="$(find_release)"', write_job.index("gh \"${publish_args[@]}\"")),
            write_job.index('verify_release_metadata "false"'),
        )
        self.assertIn('verify_release_metadata "false"', write_job)

    def test_release_seals_deterministic_terminal_assets_before_write(self) -> None:
        text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        # GitHub rejects workflow files larger than 500 KB.
        self.assertLessEqual(len(text.encode("utf-8")), 500_000)
        validate_job = text.split("\n  validate:\n", maxsplit=1)[1].split(
            "\n  verify-release-assets:\n", maxsplit=1
        )[0]
        verify_job = text.split("\n  verify-release-assets:\n", maxsplit=1)[1].split(
            "\n  release:\n", maxsplit=1
        )[0]
        write_job = text.split("\n  release:\n", maxsplit=1)[1].split(
            "\n  remote-smoke:\n", maxsplit=1
        )[0]
        self.assertIn("Build and seal deterministic terminal release assets", validate_job)
        self.assertIn(
            'python3 "${SOURCE_ROOT}/scripts/build_opencode_bundle.py"',
            validate_job,
        )
        self.assertLess(
            validate_job.index(
                'python3 -I -S "${SOURCE_ROOT}/scripts/generate_context_projections.py"'
            ),
            validate_job.index(
                'python3 "${SOURCE_ROOT}/scripts/build_opencode_bundle.py"'
            ),
        )
        self.assertLess(
            validate_job.index(
                'python3 -I -S "${rc_source_repo}/scripts/generate_context_projections.py"'
            ),
            validate_job.index(
                'python3 "${rc_source_repo}/scripts/build_opencode_bundle.py"'
            ),
        )
        # Two current-source reproducibility builds plus one conditional RC
        # rebuild that binds stable promotion to the published candidate asset.
        self.assertEqual(3, validate_job.count("scripts/build_opencode_bundle.py"))
        self.assertIn('cmp -s "${bundle}" "${repeated}"', validate_job)
        self.assertIn(
            'python3 "${SOURCE_ROOT}/scripts/generate_homebrew_formula.py"',
            validate_job,
        )
        self.assertNotIn("--client-artifacts", validate_job)
        self.assertIn('ruby -c "${formula}"', validate_job)
        for output in (
            "bundle_artifact_name",
            "bundle_checksum_name",
            "bundle_name",
            "bundle_sha256",
            "bundle_size",
            "formula_name",
            "formula_sha256",
            "formula_size",
        ):
            self.assertIn(f"echo \"{output}=", validate_job)
            self.assertIn(f"steps.bundle.outputs.{output}", text)
        self.assertIn(
            "uses: actions/upload-artifact@"
            "ea165f8d65b6e75b540449e92b4886f43607fa02 # v4.6.2",
            validate_job,
        )
        self.assertIn("id: bundle-upload", validate_job)
        self.assertIn("compression-level: 0", validate_job)
        self.assertIn("overwrite: false", validate_job)
        self.assertIn("if-no-files-found: error", validate_job)
        self.assertIn("steps.bundle-upload.outputs.artifact-id", text)
        self.assertIn("steps.bundle-upload.outputs.artifact-digest", text)
        self.assertNotIn("bundle_base64", text)
        self.assertNotIn("BUNDLE_BASE64", text)

        self.assertIn("needs: validate", verify_job)
        self.assertIn("actions: read", verify_job)
        self.assertIn("contents: read", verify_job)
        self.assertNotIn("contents: write", verify_job)
        self.assertIn("READ_TOKEN: ${{ github.token }}", verify_job)
        self.assertNotIn("GH_TOKEN: ${{ github.token }}", verify_job)
        self.assertIn(
            'python3 - "${bundle}" "${SOURCE_SHA}" <<\'PY\'', verify_job
        )
        self.assertIn("archive bytes or mode differ from immutable source", verify_job)
        self.assertIn(
            "distribution manifest is not the canonical immutable-source manifest",
            verify_job,
        )
        self.assertIn('run_git("cat-file", "blob", node[1])', verify_job)
        self.assertIn(
            'composer_path = "scripts/compose_opencode_permissions.py"',
            verify_job,
        )
        self.assertIn('composer_path: ("permission composer", 0o644)', verify_job)
        self.assertIn(
            'artifact_verifier_path = "scripts/verify_client_artifact.py"', verify_job
        )
        self.assertIn(
            'artifact_verifier_path: ("client artifact verifier", 0o755)',
            verify_job,
        )
        self.assertIn('fail(f"immutable source has no regular {label}")', verify_job)
        for mapping in (
            '"LICENSE": "LICENSE"',
            '"PROVENANCE.md": "PROVENANCE.md"',
            '"THIRD_PARTY_NOTICES.md": "THIRD_PARTY_NOTICES.md"',
            '"policy/content-lock.json": "policy/content-lock.json"',
            '"policy/client-artifacts.json": "policy/client-artifacts.json"',
        ):
            self.assertIn(mapping, verify_job)

        self.assertIn("- verify-release-assets", write_job)
        self.assertNotIn("uses:", write_job)
        self.assertNotIn("python3", write_job)
        for boundary in (verify_job, write_job):
            self.assertIn(
                '"repos/${REPOSITORY}/actions/artifacts/${BUNDLE_ARTIFACT_ID}"',
                boundary,
            )
            self.assertIn('.workflow_run.id == ($run_id | tonumber)', boundary)
            self.assertIn('.workflow_run.head_sha == $main_sha', boundary)
            self.assertIn('.digest == $digest', boundary)
            self.assertIn('unzip -Z1 "${artifact_zip}"', boundary)
            self.assertIn(
                'unzip -p "${artifact_zip}" "${BUNDLE_NAME}"', boundary
            )
            self.assertIn(
                'unzip -p "${artifact_zip}" "${FORMULA_NAME}"', boundary
            )
            self.assertIn("(( BUNDLE_SIZE <= 61000000 ))", boundary)
            self.assertIn("(( artifact_size <= 62100000 ))", boundary)
        self.assertIn("max_file_bytes = 5_000_000", verify_job)
        self.assertIn("max_distribution_bytes = 50_000_000", verify_job)
        self.assertIn("len(members) > 10000", verify_job)
        self.assertIn(
            '[[ "$(sha256sum "${bundle}" | cut -d\' \' -f1)" == "${BUNDLE_SHA256}" ]]',
            write_job,
        )
        self.assertIn('cmp -s "${expected_checksum}" "${checksum}"', write_job)
        self.assertIn("sha256sum --check --strict", write_job)
        self.assertIn(
            '[[ "$(sha256sum "${formula}" | cut -d\' \' -f1)" == "${FORMULA_SHA256}" ]]',
            write_job,
        )

        # GitHub rejects an individual run command above 21,000 characters.
        for job in (verify_job, write_job):
            for raw_script in job.split("        run: |\n")[1:]:
                raw_script = raw_script.split("\n      - name:", maxsplit=1)[0]
                self.assertLessEqual(len(textwrap.dedent(raw_script)), 21_000)

    def test_release_independently_rebuilds_formula_with_trusted_tooling(self) -> None:
        text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        verify_job = text.split(
            "\n  verify-release-assets:\n", maxsplit=1
        )[1].split("\n  release:\n", maxsplit=1)[0]
        step = verify_job.split(
            "Independently bind formula with trusted release tooling", maxsplit=1
        )[1].split(
            "Independently enforce stable rights approval", maxsplit=1
        )[0]

        for marker in (
            'git diff --name-only "${BEFORE_SHA}" "${MAIN_SHA}"',
            'git show "${MAIN_SHA}:scripts/generate_homebrew_formula.py"',
            'python3 -I -S "${trusted_generator}"',
            '--bundle-sha256 "${BUNDLE_SHA256}"',
            '"${FORMULA_SHA256}"',
            'cmp -s "${expected_formula}" "${RUNNER_TEMP}/${FORMULA_NAME}"',
        ):
            self.assertIn(marker, step)
        self.assertNotIn("client_lock", step)
        self.assertNotIn("--client-artifacts", step)
        self.assertNotIn("github.token", step)

    def test_release_approval_summary_shows_exact_sealed_values(self) -> None:
        text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        summary = text.split(
            "Write protected-environment approval summary", maxsplit=1
        )[1].split("Install checksum-pinned OpenCode CLI", maxsplit=1)[0]
        for value in (
            "REQUEST_ID",
            "CHANNEL",
            "TAG",
            "CATALOG_SHA",
            "SOURCE_SHA",
            "BUNDLE_NAME",
            "BUNDLE_SHA256",
            "BUNDLE_SIZE",
            "FORMULA_SHA256",
            "FORMULA_SIZE",
            "ARTIFACT_ID",
            "ARTIFACT_DIGEST",
        ):
            self.assertIn(value, summary)
        self.assertIn('>> "${GITHUB_STEP_SUMMARY}"', summary)

    def test_release_asset_idempotency_requires_exact_remote_bytes(self) -> None:
        text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        write_job = text.split("\n  release:\n", maxsplit=1)[1].split(
            "\n  remote-smoke:\n", maxsplit=1
        )[0]
        self.assertIn("(.assets | length) == 3", write_job)
        self.assertIn(
            '([.assets[].name] | sort) == ([$bundle, $checksum, $formula] | sort)',
            write_job,
        )
        self.assertIn('all(.assets[]; .state == "uploaded")', write_job)
        self.assertIn("verify_release_asset_roster", write_job)
        self.assertIn(".label == \"Grillmester OpenCode bundle\"", write_job)
        self.assertIn(".label == \"Homebrew formula\"", write_job)
        self.assertIn(".digest == $bundle_digest", write_job)
        self.assertIn("find_release()", write_job)
        self.assertIn('release_lookup_status}" == "4"', write_job)
        self.assertIn("return 10", write_job)
        self.assertIn("download_asset_from_release()", write_job)
        self.assertIn(
            'cmp -s "${bundle}" "${published_assets}/${BUNDLE_NAME}"',
            write_job,
        )
        self.assertIn(
            'cmp -s "${checksum}" "${published_assets}/${BUNDLE_CHECKSUM_NAME}"',
            write_job,
        )
        self.assertIn(
            'cmp -s "${formula}" "${published_assets}/${FORMULA_NAME}"',
            write_job,
        )
        self.assertIn('"${bundle}#Grillmester OpenCode bundle"', write_job)
        self.assertIn('"${checksum}#SHA-256 checksum"', write_job)
        self.assertIn('"${formula}#Homebrew formula"', write_job)
        self.assertIn("--draft --latest=false", write_job)
        self.assertIn('verify_release_metadata "true"', write_job)
        self.assertIn('gh release upload "${TAG}"', write_job)
        self.assertIn("--clobber", write_job)
        self.assertIn("--draft=false", write_job)
        self.assertLess(
            write_job.index('verify_release_metadata "true"'),
            write_job.index("--draft=false"),
        )

    def test_fixed_asset_verifier_accepts_the_canonical_builder_output(self) -> None:
        workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        marker = '          python3 - "${bundle}" "${SOURCE_SHA}" <<\'PY\'\n'
        verifier_start = workflow.index(marker) + len(marker)
        verifier_end = workflow.index("\n          PY", verifier_start)
        verifier = textwrap.dedent(workflow[verifier_start:verifier_end])

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            (source / "scripts").mkdir(parents=True)
            for name in (
                "build_opencode_bundle.py",
                "compose_opencode_permissions.py",
                "generate_context_projections.py",
                "grillmester.py",
                "grillmester_local.py",
                "manage_opencode.py",
                "smoke_grillmester_local.py",
                "verify_client_artifact.py",
            ):
                shutil.copy2(ROOT / "scripts" / name, source / "scripts" / name)
            shutil.copy2(ROOT / "LICENSE", source / "LICENSE")
            shutil.copy2(ROOT / "PROVENANCE.md", source / "PROVENANCE.md")
            shutil.copy2(
                ROOT / "THIRD_PARTY_NOTICES.md",
                source / "THIRD_PARTY_NOTICES.md",
            )
            shutil.copytree(ROOT / "plugin", source / "plugin")
            (source / "policy").mkdir(parents=True)
            for name in (
                "client-artifacts.json",
                "content-lock.json",
                "focused-context-v1.json",
            ):
                shutil.copy2(ROOT / "policy" / name, source / "policy" / name)
            shutil.copytree(ROOT / "profiles", source / "profiles")
            shutil.copytree(ROOT / "targets", source / "targets")
            subprocess.run(["git", "init", "--quiet", str(source)], check=True)
            subprocess.run(["git", "-C", str(source), "add", "--all"], check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(source),
                    "add",
                    "--force",
                    "targets/opencode-v1/.gitignore",
                    "targets/opencode-v1-focused/.gitignore",
                ],
                check=True,
            )
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(source),
                    "-c",
                    "user.name=workflow-test",
                    "-c",
                    "user.email=workflow-test@example.invalid",
                    "commit",
                    "--quiet",
                    "-m",
                    "fixture",
                ],
                check=True,
            )
            source_sha = subprocess.run(
                ["git", "-C", str(source), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            bundle = root / "canonical.tar.gz"
            built = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/build_opencode_bundle.py"),
                    "--source-root",
                    str(source),
                    "--source-sha",
                    source_sha,
                    "--output",
                    str(bundle),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(built.returncode, 0, built.stderr)
            verified = subprocess.run(
                [sys.executable, "-", str(bundle), source_sha],
                cwd=source,
                input=verifier,
                capture_output=True,
                text=True,
            )
            self.assertEqual(verified.returncode, 0, verified.stderr)

            raw_tar = bytearray(gzip.decompress(bundle.read_bytes()))
            with tarfile.open(fileobj=io.BytesIO(raw_tar), mode="r:") as archive:
                regular = next(
                    member
                    for member in archive.getmembers()
                    if member.type == tarfile.REGTYPE
                )

            for type_flag in (tarfile.CONTTYPE, tarfile.GNUTYPE_SPARSE):
                with self.subTest(type_flag=type_flag):
                    mutated_tar = bytearray(raw_tar)
                    header_start = regular.offset
                    mutated_tar[header_start + 156 : header_start + 157] = type_flag
                    mutated_tar[header_start + 148 : header_start + 156] = b" " * 8
                    checksum = sum(mutated_tar[header_start : header_start + 512])
                    mutated_tar[header_start + 148 : header_start + 156] = (
                        f"{checksum:06o}\0 ".encode("ascii")
                    )
                    mutated = root / f"special-{type_flag.hex()}.tar.gz"
                    with mutated.open("wb") as output:
                        with gzip.GzipFile(
                            filename="",
                            mode="wb",
                            compresslevel=9,
                            fileobj=output,
                            mtime=0,
                        ) as compressed:
                            compressed.write(mutated_tar)
                    rejected = subprocess.run(
                        [sys.executable, "-", str(mutated), source_sha],
                        cwd=source,
                        input=verifier,
                        capture_output=True,
                        text=True,
                    )
                    self.assertNotEqual(rejected.returncode, 0, rejected.stderr)
                    self.assertIn("special", rejected.stderr.lower())

    def test_remote_smoke_verifies_and_safely_installs_release_asset(self) -> None:
        text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        remote = text.split("\n  remote-smoke:\n", maxsplit=1)[1]
        self.assertIn(
            "Download, verify, safely extract, and install OpenCode asset", remote
        )
        self.assertIn("--proto '=https' --tlsv1.2", remote)
        self.assertIn("--proto-redir '=https'", remote)
        self.assertIn("--max-filesize 61000000", remote)
        self.assertIn("--max-filesize 1024", remote)
        self.assertIn("--max-filesize 100000", remote)
        self.assertIn('cmp -s "${expected_checksum}" "${checksum}"', remote)
        self.assertIn("sha256sum --check --strict", remote)
        self.assertIn("scripts/generate_homebrew_formula.py", remote)
        self.assertIn('cmp -s "${expected_formula}" "${formula}"', remote)
        self.assertIn("links and special archive nodes are forbidden", remote)
        self.assertIn("member.type == tarfile.DIRTYPE", remote)
        self.assertIn(
            "member.type not in (tarfile.REGTYPE, tarfile.DIRTYPE)", remote
        )
        self.assertIn("archive member escapes extraction root", remote)
        self.assertIn("archive expands beyond the safety limit", remote)
        self.assertIn("distribution manifest provenance does not match", remote)
        self.assertIn("extracted files do not match the distribution manifest", remote)
        self.assertIn(
            'python3 -I -S "${bundle_root}/scripts/manage_opencode.py" install', remote
        )
        self.assertIn('--source "${bundle_root}"', remote)
        self.assertNotIn('--source "${bundle_root}/targets/opencode-v1"', remote)
        self.assertIn('--home "${install_home}"', remote)

    def test_stable_release_cannot_drift_terminal_distribution_inputs(self) -> None:
        text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        verify_job = text.split("\n  verify-release-assets:\n", maxsplit=1)[1].split(
            "\n  release:\n", maxsplit=1
        )[0]
        write_job = text.split("\n  release:\n", maxsplit=1)[1].split(
            "\n  remote-smoke:\n", maxsplit=1
        )[0]
        for path in (
            "targets/opencode-v1",
            "targets/opencode-v1-focused",
            "profiles/opencode",
            "policy/focused-context-v1.json",
            "scripts/generate_context_projections.py",
            "scripts/grillmester_local.py",
        ):
            self.assertIn(path, write_job)
        self.assertIn("targets/copilot-cli-focused-v1", verify_job)
        self.assertIn("stable_focused_digest", verify_job)
        self.assertIn(
            "scripts/compose_opencode_permissions.py scripts/release_contract.py",
            write_job,
        )
        self.assertIn("scripts/generate_homebrew_formula.py", write_job)
        for harness in (
            "scripts/smoke_plugin_install.py",
            "scripts/smoke_opencode.py",
            "scripts/smoke_opencode_runtime.py",
            "scripts/smoke_grillmester_local.py",
            "scripts/smoke_grillmester_tui.py",
        ):
            self.assertIn(harness, write_job)
        for path in (
            "LICENSE",
            "PROVENANCE.md",
            "THIRD_PARTY_NOTICES.md",
            "policy/content-lock.json",
            "policy/client-artifacts.json",
        ):
            self.assertIn(path, write_job)

    def test_stable_rights_gate_is_independent_and_recomputes_immutable_scope(self) -> None:
        text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        verify_job = text.split("\n  verify-release-assets:\n", maxsplit=1)[1].split(
            "\n  release:\n", maxsplit=1
        )[0]
        self.assertIn("Independently enforce stable rights approval", verify_job)
        self.assertIn('blob("policy/stable-rights-approval.json")', verify_job)
        self.assertIn('git("ls-tree", "-rz", source_sha, "--", prefix)', verify_job)
        self.assertIn("expected_components[kind][component_id] = component_digest", verify_job)
        self.assertIn("scope[\"components\"] != expected_components", verify_job)
        self.assertIn("dt.date.fromisoformat", verify_job)
        self.assertIn("decision_date > dt.date.today()", verify_job)

    def test_stable_promotion_rebinds_the_published_rc_assets(self) -> None:
        text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        preflight = PROMOTE_WORKFLOW.read_text(encoding="utf-8")
        validate_job = text.split("\n  validate:\n", maxsplit=1)[1].split(
            "\n  release:\n", maxsplit=1
        )[0]
        write_job = text.split("\n  release:\n", maxsplit=1)[1].split(
            "\n  remote-smoke:\n", maxsplit=1
        )[0]
        self.assertIn('rc_bundle_name="grillmester-opencode-${rc_tag}.tar.gz"', validate_job)
        self.assertIn(
            'python3 "${rc_source_repo}/scripts/build_opencode_bundle.py"',
            validate_job,
        )
        self.assertIn(
            'cmp -s "${rc_rebuilt_bundle}" "${rc_published_bundle}"',
            validate_job,
        )
        self.assertIn("rc_bundle_sha256=", validate_job)
        self.assertIn("rc_bundle_checksum_sha256=", validate_job)
        for output in (
            "rc_bundle_name",
            "rc_bundle_sha256",
            "rc_bundle_checksum_name",
            "rc_bundle_checksum_sha256",
            "rc_formula_sha256",
        ):
            self.assertIn(f"steps.contract.outputs.{output}", text)
        self.assertIn('.digest == $bundle_digest', write_job)
        self.assertIn('gh release download "${RC_TAG}"', write_job)
        self.assertIn('"${RC_BUNDLE_SHA256}"', write_job)
        self.assertIn('"${RC_BUNDLE_CHECKSUM_SHA256}"', write_job)
        self.assertIn('git cat-file -t "refs/tags/${rc_tag}"', validate_job)
        self.assertIn('git cat-file -t "refs/tags/${RC_TAG}"', preflight)
        self.assertIn('git cat-file -t "refs/tags/${RC_TAG}"', write_job)
        for workflow in (validate_job, preflight):
            self.assertIn("(.assets | length) == 3", workflow)
            self.assertIn('[[ "$(jq -r \'.immutable\' <<<"${rc_release}")" == "true" ]]', workflow)
            self.assertIn('.label == "Grillmester OpenCode bundle"', workflow)
            self.assertIn('.label == "SHA-256 checksum"', workflow)
            self.assertIn('.label == "Homebrew formula"', workflow)
            self.assertIn(".browser_download_url", workflow)
            self.assertIn('--proto \'=https\' --tlsv1.2', workflow)
            self.assertIn("--proto-redir '=https'", workflow)
            self.assertIn("--max-filesize 61000000", workflow)
            self.assertIn("--max-filesize 1024", workflow)
            self.assertIn("--max-filesize 100000", workflow)
            self.assertIn(
                'python3 "${rc_source_repo}/scripts/build_opencode_bundle.py"',
                workflow,
            )
            self.assertIn(
                'cmp -s "${rc_rebuilt_bundle}" "${rc_published_bundle}"',
                workflow,
            )
            self.assertIn("scripts/generate_homebrew_formula.py", workflow)
            self.assertIn(
                'cmp -s "${rc_expected_formula}" "${rc_published_formula}"',
                workflow,
            )
            self.assertLess(
                workflow.index(
                    "Complete the workflow-owned, read-only contract before executing"
                ),
                workflow.index('python3 "${rc_source_repo}/scripts/build_opencode_bundle.py"'),
            )

    def test_release_validates_one_complete_plugin_and_remote_smokes_tag(self) -> None:
        text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('--source-root "${SOURCE_ROOT}"', text)
        self.assertNotIn("--source-plugin", text)
        self.assertGreaterEqual(
            text.count('[.plugins[].name] == ["grillmester"]'),
            2,
        )
        self.assertNotIn('path: "plugin-nav"', text)
        self.assertIn(
            '{name: "grillmester", path: "plugin", agents: 7, skills: 42}',
            text,
        )
        self.assertIn(
            '(keys | sort) == ["marketplace", "packages", "schemaVersion"]',
            text,
        )
        self.assertIn(
            '"agents", "author", "description", "license", "name",', text
        )
        self.assertEqual(1, text.count('(.author | keys) == ["name"]'))
        self.assertIn("Smoke-test published release tag", text)
        self.assertIn(
            '--remote-marketplace-ref "navikt/grillmester#${TAG}"', text
        )


if __name__ == "__main__":
    unittest.main()
