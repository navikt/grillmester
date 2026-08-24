from __future__ import annotations

import importlib.util
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "grillmester_tui_smoke", ROOT / "scripts/smoke_grillmester_tui.py"
)
assert SPEC is not None and SPEC.loader is not None
SMOKE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SMOKE)


class GrillmesterTuiSmokeTest(unittest.TestCase):
    def test_launcher_owns_no_audit_hardening(self) -> None:
        command = SMOKE._launcher_command(
            launcher=Path("/opt/homebrew/bin/grillmester"),
            project_dir=Path("/tmp/consumer"),
        )

        self.assertNotIn("--no-audit", command)
        self.assertIn("--preset", command)

    def test_ready_requires_the_selected_version_and_tui_markers(self) -> None:
        marker = SMOKE._version_marker("1.19.3")

        self.assertTrue(
            SMOKE._is_ready(
                b"Ask anything Grillmester 1.19.3", opencode_version=marker
            )
        )
        self.assertFalse(
            SMOKE._is_ready(b"Ask anything Grillmester", opencode_version=marker)
        )
        self.assertFalse(
            SMOKE._is_ready(
                b"Ask anything Grillmester 1.18.20", opencode_version=marker
            )
        )
        self.assertFalse(
            SMOKE._is_ready(b"Unexpected server error", opencode_version=marker)
        )

    def test_version_marker_rejects_non_semantic_output(self) -> None:
        with self.assertRaisesRegex(SMOKE.TuiSmokeError, "semantic version"):
            SMOKE._version_marker("OpenCode latest")

    def test_environment_stages_exact_clients_under_their_cli_names(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            launcher_bin = root / "launcher-bin"
            cellar_bin = root / "Cellar/opencode/1.18.20/libexec/bin"
            cplt_bin = root / "Cellar/cplt/2026/bin"
            state = root / "state"
            launcher_bin.mkdir()
            cellar_bin.mkdir(parents=True)
            cplt_bin.mkdir(parents=True)
            state.mkdir()
            opencode = cellar_bin / "opencode.exe"
            cplt = cplt_bin / "cplt-real"
            for executable in (opencode, cplt):
                executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                executable.chmod(0o700)
            environment = SMOKE._environment(
                state,
                opencode=opencode,
                cplt=cplt,
            )

            path = environment["PATH"].split(":")
            self.assertEqual(str(state / "client-bin"), path[0])
            self.assertNotIn("/opt/homebrew/bin", path)
            self.assertNotIn("/usr/local/bin", path)
            self.assertEqual(
                ["/usr/bin", "/bin", "/usr/sbin", "/sbin"], path[-4:]
            )
            self.assertEqual(
                opencode.resolve(),
                SMOKE._resolved_on_path("opencode", environment),
            )
            self.assertEqual(
                cplt.resolve(), SMOKE._resolved_on_path("cplt", environment)
            )

    def test_pty_smoke_stops_a_ready_session_and_checks_runtime_support(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binaries = root / "bin"
            project = root / "project"
            state = root / "state"
            binaries.mkdir()
            (project / ".git").mkdir(parents=True)
            state.mkdir()
            for name in ("cplt", "opencode"):
                executable = binaries / name
                executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                executable.chmod(0o700)
            launcher = binaries / "grillmester"
            launcher.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env python3
                    import os
                    import signal
                    import time
                    from pathlib import Path

                    config = Path(os.environ["XDG_CONFIG_HOME"]) / "opencode"
                    config.mkdir(parents=True)
                    (config / ".gitignore").write_bytes(
                        b"node_modules\\npackage.json\\npackage-lock.json\\nbun.lock\\n.gitignore\\n"
                    )
                    signal.signal(signal.SIGINT, lambda *_arguments: raise_exit())

                    def raise_exit():
                        raise SystemExit(0)

                    print("Ask anything Grillmester 1.18.20", flush=True)
                    while True:
                        time.sleep(0.1)
                    """
                ),
                encoding="utf-8",
            )
            launcher.chmod(0o700)

            SMOKE.run_tui_smoke(
                launcher=launcher,
                opencode=binaries / "opencode",
                opencode_version="1.18.20",
                cplt=binaries / "cplt",
                project_dir=project,
                state_parent=state,
                startup_timeout=3,
                exit_timeout=3,
            )
            self.assertEqual([], list(state.iterdir()))


if __name__ == "__main__":
    unittest.main()
