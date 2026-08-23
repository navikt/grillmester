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
    def test_ready_requires_the_pinned_tui_and_grillmester_markers(self) -> None:
        self.assertTrue(SMOKE._is_ready(b"Ask anything Grillmester 1.18.20"))
        self.assertFalse(SMOKE._is_ready(b"Ask anything Grillmester"))
        self.assertFalse(SMOKE._is_ready(b"Unexpected server error"))

    def test_environment_excludes_ambient_homebrew_prefixes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binaries = root / "bin"
            state = root / "state"
            binaries.mkdir()
            state.mkdir()
            environment = SMOKE._environment(
                state,
                launcher=binaries / "grillmester",
                opencode=binaries / "opencode",
                cplt=binaries / "cplt",
            )

        path = environment["PATH"].split(":")
        self.assertEqual(str(binaries), path[0])
        self.assertNotIn("/opt/homebrew/bin", path)
        self.assertNotIn("/usr/local/bin", path)
        self.assertEqual(["/usr/bin", "/bin", "/usr/sbin", "/sbin"], path[-4:])

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
                cplt=binaries / "cplt",
                project_dir=project,
                state_parent=state,
                startup_timeout=3,
                exit_timeout=3,
            )
            self.assertEqual([], list(state.iterdir()))


if __name__ == "__main__":
    unittest.main()
