#!/usr/bin/env python3
"""Prove that the installed launcher reaches OpenCode's TUI through cplt."""

from __future__ import annotations

import argparse
import errno
import fcntl
import os
import pty
import select
import shutil
import signal
import struct
import sys
import tempfile
import termios
import time
from pathlib import Path
from typing import Mapping, Sequence


MAX_OUTPUT_BYTES = 2 * 1024 * 1024
OPENCODE_RUNTIME_GITIGNORE = (
    b"node_modules\npackage.json\npackage-lock.json\nbun.lock\n.gitignore\n"
)
READY_MARKERS = (b"Ask anything", b"Grillmester", b"1.18.20")
FAILURE_MARKERS = (
    b"unexpected server error",
    b"operation not permitted",
    b"traceback (most recent call last)",
)


class TuiSmokeError(RuntimeError):
    """Raised when the native PTY launch does not reach a usable TUI."""


def _regular_executable(path: Path, *, label: str) -> Path:
    try:
        resolved = path.resolve(strict=True)
        observed = resolved.stat()
    except OSError as exc:
        raise TuiSmokeError(f"could not inspect {label}: {exc}") from exc
    if not resolved.is_file() or not observed.st_mode & 0o111:
        raise TuiSmokeError(f"{label} must be an executable regular file: {resolved}")
    return resolved


def _environment(
    state: Path, *, launcher: Path, opencode: Path, cplt: Path
) -> dict[str, str]:
    home = state / "home"
    config = state / "config"
    data = state / "data"
    cache = state / "cache"
    runtime_state = state / "runtime-state"
    for directory in (home, config, data, cache, runtime_state, config / "cplt"):
        directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    cplt_config = config / "cplt/config.toml"
    cplt_config.write_bytes(b"")
    cplt_config.chmod(0o600)

    path_entries: list[str] = []
    for directory in (launcher.parent, opencode.parent, cplt.parent):
        value = str(directory)
        if value not in path_entries:
            path_entries.append(value)
    path_entries.extend(("/usr/bin", "/bin", "/usr/sbin", "/sbin"))
    return {
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(config),
        "XDG_DATA_HOME": str(data),
        "XDG_CACHE_HOME": str(cache),
        "XDG_STATE_HOME": str(runtime_state),
        "CPLT_CONFIG": str(cplt_config),
        "PATH": ":".join(path_entries),
        "TERM": "xterm-256color",
        "LANG": "en_US.UTF-8",
    }


def _resolved_on_path(name: str, environment: Mapping[str, str]) -> Path:
    resolved = shutil.which(name, path=environment["PATH"])
    if resolved is None:
        raise TuiSmokeError(f"{name} is absent from the isolated PATH")
    try:
        return Path(resolved).resolve(strict=True)
    except OSError as exc:
        raise TuiSmokeError(f"could not resolve isolated {name}: {exc}") from exc


def _is_ready(output: bytes) -> bool:
    return all(marker in output for marker in READY_MARKERS)


def _bounded_excerpt(output: bytes) -> str:
    tail = output[-16_384:].decode("utf-8", errors="replace")
    return tail.replace("\x00", "")


def _terminate_child(child_pid: int, *, grace_seconds: float = 2.0) -> int:
    def send(signal_number: signal.Signals) -> None:
        try:
            process_group = os.getpgid(child_pid)
            if process_group == child_pid:
                os.killpg(process_group, signal_number)
            else:
                os.kill(child_pid, signal_number)
        except ProcessLookupError:
            pass

    try:
        send(signal.SIGTERM)
    except OSError:
        return os.waitpid(child_pid, 0)[1]
    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline:
        observed, observed_status = os.waitpid(child_pid, os.WNOHANG)
        if observed:
            return observed_status
        time.sleep(0.05)
    send(signal.SIGKILL)
    return os.waitpid(child_pid, 0)[1]


def _run_tui_smoke_in_state(
    *,
    launcher: Path,
    opencode: Path,
    cplt: Path,
    project_dir: Path,
    state: Path,
    startup_timeout: float = 25.0,
    exit_timeout: float = 8.0,
) -> None:
    launcher = _regular_executable(launcher, label="launcher")
    opencode = _regular_executable(opencode, label="OpenCode")
    cplt = _regular_executable(cplt, label="cplt")
    try:
        project_dir = project_dir.resolve(strict=True)
        state = state.resolve(strict=True)
    except OSError as exc:
        raise TuiSmokeError(f"could not resolve smoke directory: {exc}") from exc
    if not project_dir.is_dir() or not (project_dir / ".git").is_dir():
        raise TuiSmokeError("project-dir must be an initialized Git worktree")
    if not state.is_dir():
        raise TuiSmokeError("state must be a directory")
    environment = _environment(
        state, launcher=launcher, opencode=opencode, cplt=cplt
    )
    if _resolved_on_path("opencode", environment) != opencode:
        raise TuiSmokeError("isolated PATH does not select the reviewed OpenCode binary")
    if _resolved_on_path("cplt", environment) != cplt:
        raise TuiSmokeError("isolated PATH does not select the reviewed cplt binary")

    command = [
        str(launcher),
        "--client",
        "opencode",
        "--agent",
        "grillmester",
        "--project-dir",
        str(project_dir),
        "--yes",
        "--quiet",
        "--no-audit",
        "--preset",
        "strict",
        "--",
        "--print-logs",
        "--log-level",
        "INFO",
    ]
    child_pid, descriptor = pty.fork()
    if child_pid == 0:
        os.chdir(project_dir)
        os.execve(command[0], command, environment)

    fcntl.ioctl(descriptor, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 100, 0, 0))
    output = bytearray()
    child_status: int | None = None
    interrupted = False
    startup_deadline = time.monotonic() + startup_timeout
    exit_deadline = 0.0
    try:
        while child_status is None:
            now = time.monotonic()
            if not interrupted and _is_ready(output):
                os.write(descriptor, b"\x03")
                interrupted = True
                exit_deadline = now + exit_timeout
            elif not interrupted and now >= startup_deadline:
                raise TuiSmokeError(
                    "OpenCode TUI did not become ready before timeout:\n"
                    + _bounded_excerpt(output)
                )
            elif interrupted and now >= exit_deadline:
                raise TuiSmokeError("OpenCode TUI did not exit after Ctrl-C")

            ready, _, _ = select.select([descriptor], [], [], 0.2)
            if ready:
                try:
                    chunk = os.read(descriptor, 65_536)
                except OSError as exc:
                    if exc.errno != errno.EIO:
                        raise
                    chunk = b""
                output.extend(chunk)
                if len(output) > MAX_OUTPUT_BYTES:
                    raise TuiSmokeError("OpenCode TUI output exceeded the safety limit")
                lowered = bytes(output).lower()
                for marker in FAILURE_MARKERS:
                    if marker in lowered:
                        raise TuiSmokeError(
                            f"OpenCode TUI emitted {marker.decode()!r}:\n"
                            + _bounded_excerpt(output)
                        )
            observed, observed_status = os.waitpid(child_pid, os.WNOHANG)
            if observed:
                child_status = observed_status
    finally:
        if child_status is None:
            child_status = _terminate_child(child_pid)
        os.close(descriptor)

    if not _is_ready(output):
        raise TuiSmokeError(
            "OpenCode exited before rendering the Grillmester TUI:\n"
            + _bounded_excerpt(output)
        )
    assert child_status is not None
    exit_code = os.waitstatus_to_exitcode(child_status)
    if exit_code != 0:
        raise TuiSmokeError(f"OpenCode TUI exited with {exit_code}")
    support = Path(environment["XDG_CONFIG_HOME"]) / "opencode/.gitignore"
    try:
        content = support.read_bytes()
    except OSError as exc:
        raise TuiSmokeError(f"launcher did not pre-seed OpenCode runtime support: {exc}") from exc
    if content != OPENCODE_RUNTIME_GITIGNORE or support.is_symlink():
        raise TuiSmokeError("OpenCode runtime support file is not the reviewed regular payload")


def run_tui_smoke(
    *,
    launcher: Path,
    opencode: Path,
    cplt: Path,
    project_dir: Path,
    state_parent: Path,
    startup_timeout: float = 25.0,
    exit_timeout: float = 8.0,
) -> None:
    try:
        state_parent = state_parent.resolve(strict=True)
    except OSError as exc:
        raise TuiSmokeError(f"could not resolve state parent: {exc}") from exc
    if not state_parent.is_dir():
        raise TuiSmokeError("state-parent must be a directory")
    with tempfile.TemporaryDirectory(
        prefix="grillmester-tui-", dir=state_parent
    ) as state:
        _run_tui_smoke_in_state(
            launcher=launcher,
            opencode=opencode,
            cplt=cplt,
            project_dir=project_dir,
            state=Path(state),
            startup_timeout=startup_timeout,
            exit_timeout=exit_timeout,
        )


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--launcher", type=Path, required=True)
    parser.add_argument("--opencode", type=Path, required=True)
    parser.add_argument("--cplt", type=Path, required=True)
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--state-parent", type=Path, required=True)
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    options = parse_arguments(arguments)
    try:
        run_tui_smoke(
            launcher=options.launcher,
            opencode=options.opencode,
            cplt=options.cplt,
            project_dir=options.project_dir,
            state_parent=options.state_parent,
        )
    except (TuiSmokeError, OSError) as exc:
        print(f"Grillmester TUI smoke failed: {exc}", file=sys.stderr)
        return 1
    print("Grillmester TUI smoke passed through cplt without a model call.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
