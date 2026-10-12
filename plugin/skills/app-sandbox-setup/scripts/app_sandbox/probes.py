"""Behavioral verification in the caller's session."""

from __future__ import annotations

import errno
import os
import re
import socket
import tempfile
import threading
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from . import discovery, project_probes, rules
from .paths import under


def probe_result(action: Any) -> str:
    try:
        action()
        return "OK"
    except OSError as error:
        return "denied" if error.errno in (errno.EPERM, errno.EACCES) else "error"


def probe_write(directory: Path) -> str:
    def action() -> None:
        descriptor, name = tempfile.mkstemp(prefix=".app-sandbox-verify-", dir=str(directory))
        try:
            os.write(descriptor, b"probe")
        finally:
            try:
                os.close(descriptor)
            finally:
                os.unlink(name)
    return probe_result(action)


def probe_db_open(db: Path) -> str:
    def action() -> None:
        # Opening is the entire probe; never read even one byte or query SQLite.
        with db.open("rb"):
            pass
    return probe_result(action)


def probe_loopback() -> str:
    def action() -> None:
        errors = []
        with socket.socket() as server:
            server.settimeout(1)
            server.bind(("127.0.0.1", 0))
            server.listen(1)

            def exchange() -> None:
                try:
                    peer, _ = server.accept()
                    with peer:
                        peer.settimeout(1)
                        if peer.recv(1) != b"x":
                            raise OSError("probe exchange failed")
                        peer.sendall(b"y")
                except OSError as error:
                    errors.append(error)

            thread = threading.Thread(target=exchange, daemon=True)
            thread.start()
            try:
                with socket.create_connection(server.getsockname(), timeout=1) as client:
                    client.sendall(b"x")
                    if client.recv(1) != b"y":
                        raise OSError("probe exchange failed")
            finally:
                thread.join(timeout=2)
            if errors:
                raise errors[0]
    return probe_result(action)


def behavioral_probes(home: Path, db: Path) -> dict[str, str]:
    cache = next((path for path in (home / ".gradle", home / ".m2", home / "Library/Caches", Path("/tmp"))
                  if path.is_dir()), None)
    hardened = next((path for path in [home / ".config/git", *discovery.hardened_cache_paths(home),
                                       *(home / relative for relative in rules.HARDENING_READONLY),
                                       *(home / relative for relative in rules.RO_PATHS)]
                     if under(path, home) and path.is_dir()), None)
    return {
        "HOME write": probe_write(home), "DB open": probe_db_open(db), "loopback": probe_loopback(),
        "cache write": probe_write(cache) if cache else "unavailable",
        "readonly write": probe_write(hardened) if hardened else "unavailable",
    }


def token_format(value: str) -> str:
    """Classify GH_TOKEN by shape only; never return any part of the value."""
    if not value:
        return "absent"
    if re.fullmatch(r"gh[opusr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,}", value):
        # A placeholder could share this shape; callers must not treat it as proof.
        return "GitHub token shape"
    return "other (placeholder?)"


def verify(home: Path, db: Path, mask: bool, toolchain: bool = True) -> int:
    expected = {"HOME write": "denied", "DB open": "denied",
                "loopback": "denied" if mask else "OK", "cache write": "OK", "readonly write": "denied"}
    actual = behavioral_probes(home, db)
    print(f"Masking expectation: {'ON' if mask else 'OFF'}")
    print("probe | expected | actual")
    for name, value in expected.items():
        print(f"{name} | {value} | {actual[name]}")
    loopback_proxy = False
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        try:
            loopback_proxy |= urlsplit(os.environ.get(key, "")).hostname in ("127.0.0.1", "localhost", "::1")
        except ValueError:
            pass
    print("proxy env points to loopback: " + ("yes" if loopback_proxy else "no"))
    token = token_format(os.environ.get("GH_TOKEN", ""))
    print("GH_TOKEN set: " + ("no" if token == "absent" else "yes"))
    print("GH_TOKEN format: " + token)
    # Heuristics from live observation, not documented app behavior. Unsandboxed
    # sessions always have loopback and no proxy, so hints would contradict that line.
    sandboxed = actual["HOME write"] != "OK"
    if sandboxed and token == "GitHub token shape" and not loopback_proxy:
        print("GH_TOKEN has a GitHub token shape and no loopback proxy is set: "
              "sandboxed processes can likely read a real token.")
    if sandboxed and not mask and loopback_proxy and actual["loopback"] == "denied":
        print("Loopback is denied behind a loopback proxy: masking is likely ON. "
              "If so, rerun verify with --mask-credentials.")
    if sandboxed and mask and actual["loopback"] == "OK":
        print("Loopback works although --mask-credentials was given: masking is likely OFF "
              "for this project. Compare with the plan's masking line; if OFF, rerun verify without the flag.")
    project_results = project_probes.run(Path.cwd(), home) if toolchain else []
    if not toolchain:
        print("Toolchain probes skipped (--no-toolchain).")
    for result in project_results:
        role = "gate" if result["gate"] else f'info ({result["info"]})'
        print(f'{result["name"]} | {role} | ok (version {result["expected"]}) | '
              f'{result["category"]} (version {result["actual"]})')
    if actual["HOME write"] == "OK":
        print("this session is not sandboxed: start a new session or use /sandbox on.")
    print("Differences can be caused by enterprise managed settings. Verify in a NEW sandboxed session; unavailable/error probes do not prove protection.")
    gating_ok = all(result["category"] == "ok" for result in project_results if result["gate"])
    return 0 if actual == expected and gating_ok else 7
