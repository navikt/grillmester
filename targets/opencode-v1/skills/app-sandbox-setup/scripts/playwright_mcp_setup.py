#!/usr/bin/env python3
"""Plan and explicitly confirm installation of the two Playwright MCP wrappers."""

import argparse
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import subprocess
import tempfile
from urllib.parse import urlsplit


PW_VERSION = "1.63.0"
MCP_VERSION = "0.0.80"
IMAGE = "mcr.microsoft.com/playwright:v" + PW_VERSION + "-noble"
SCRIPTS = Path(__file__).resolve().parent
NEW_ENDPOINT = "ws://127.0.0.1:53333/<generated-token>"


class UsageError(Exception):
    pass


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default diagnostic echoes arbitrary user input.
        raise UsageError()


def check_path(path, directory=False):
    """Refuse symlinks and wrong types before reading or replacing any target."""
    for parent in reversed(path.parents):
        if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
            raise OSError("Unsafe parent.")
    try:
        observed = path.lstat()
    except FileNotFoundError:
        return
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected(observed.st_mode):
        raise OSError("Unsafe target.")


def encoded(value, canonical=False):
    return (json.dumps(value, sort_keys=canonical, indent=2, ensure_ascii=False) + "\n").encode()


def read_regular(path):
    """Read a snapshot without following a swapped final symlink or blocking on a FIFO."""
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None, None
    with os.fdopen(descriptor, "rb") as stream:
        observed = os.fstat(stream.fileno())
        if not stat.S_ISREG(observed.st_mode):
            raise OSError("Not a regular file.")
        content = stream.read()
        after = os.fstat(stream.fileno())
        fields = ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns", "st_ctime_ns")
        if any(getattr(observed, field) != getattr(after, field) for field in fields):
            raise OSError("File changed while reading.")
        return content, stat.S_IMODE(observed.st_mode)


def find_docker(home):
    discovered = shutil.which("docker")
    if discovered:
        return discovered
    for directory in (home / ".rd/bin", home / ".orbstack/bin",
                      Path("/opt/homebrew/bin"), Path("/usr/local/bin"),
                      Path("/Applications/Docker.app/Contents/Resources/bin")):
        candidate = directory / "docker"
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def image_warning(home):
    docker = find_docker(home)
    if not docker:
        return "Docker unavailable: install/start Docker before using the sandbox server."
    try:
        result = subprocess.run([docker, "image", "inspect", IMAGE], timeout=3,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if result.returncode == 0:
            return "Docker image is present: " + IMAGE + "."
        daemon = subprocess.run([docker, "info", "--format", "{{.ServerVersion}}"], timeout=3,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if daemon.returncode != 0:
            return "Docker is not running or is inaccessible: start it outside the sandbox."
        return ("Image missing: run docker pull " + IMAGE + " OUTSIDE the sandbox "
                "(normal terminal, or approve Run outside the sandbox → Run once).")
    except subprocess.TimeoutExpired:
        return "Docker check timed out: check Docker outside the sandbox."
    except OSError:
        return "Docker unavailable or inaccessible: check it outside the sandbox."


def read_object(path):
    content, _ = read_regular(path)
    if content is None:
        return {}
    value = json.loads(content.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object.")
    return value


def valid_endpoint(endpoint):
    if not isinstance(endpoint, str):
        return False
    try:
        url = urlsplit(endpoint)
        return (url.scheme == "ws" and url.hostname == "127.0.0.1"
                and url.username is None and url.password is None
                and url.port is not None and 1 <= url.port <= 65535
                and not url.query and not url.fragment
                and re.fullmatch(r"/[A-Za-z0-9_-]{32,}", url.path) is not None)
    except ValueError:
        return False


def build_plan(home, mcp_config, bin_dir):
    if bin_dir == home or home not in bin_dir.parents:
        raise OSError("bin-dir must be inside home.")
    check_path(bin_dir, directory=True)
    check_path(mcp_config)
    check_path(home / ".config/playwright-mcp/docker.json")
    check_path(home / ".copilot/app-sandbox-setup-backups", directory=True)
    for name in ("playwright-mcp-docker", "playwright-mcp-headed"):
        check_path(bin_dir / name)
    mcp = read_object(mcp_config)
    servers = mcp.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise ValueError("mcpServers must be an object.")
    docker_path = home / ".config/playwright-mcp/docker.json"
    docker = read_object(docker_path)
    browser = docker.setdefault("browser", {})
    if not isinstance(browser, dict):
        raise ValueError("browser must be an object.")
    changes = []

    def show_override(source, key, desired, label):
        if key in source and source[key] != desired:
            changes.append({"file": str(docker_path), "action": "change browser option",
                            "option": label, "before": source[key], "after": desired})

    show_override(browser, "isolated", True, "browser.isolated")
    show_override(browser, "browserName", "chromium", "browser.browserName")
    remote = browser.get("remoteEndpoint", {})
    if isinstance(remote, dict):
        show_override(remote, "exposeNetwork", "<loopback>", "remoteEndpoint.exposeNetwork")
        show_override(remote, "browserName", "chromium", "remoteEndpoint.browserName")
    elif isinstance(remote, str):
        changes.append({"file": str(docker_path),
                        "action": "replace string-valued remoteEndpoint with an object (endpoint redacted)"})
    endpoint = remote.get("endpoint") if isinstance(remote, dict) else None
    if not valid_endpoint(endpoint):
        endpoint = NEW_ENDPOINT
    browser["isolated"] = True
    browser["browserName"] = "chromium"
    merged_remote = copy.deepcopy(remote) if isinstance(remote, dict) else {}
    merged_remote.update(endpoint=endpoint, browserName="chromium", exposeNetwork="<loopback>")
    browser["remoteEndpoint"] = merged_remote
    argument_warnings = []
    writes = []
    states = []

    def install(path, content, mode, label):
        old, old_mode = read_regular(path)
        states.append([str(path), hashlib.sha256(old).hexdigest() if old is not None else None, old_mode])
        if old != content or old_mode != mode:
            writes.append((path, content, mode))
            changes.append(label)

    for server_id, name, args in (
        ("playwright-sandbox", "playwright-mcp-docker", []),
        ("com.microsoft/playwright-mcp", "playwright-mcp-headed", ["--isolated", "--browser", "chromium"]),
    ):
        source = SCRIPTS / name
        wrapper = bin_dir / name
        install(wrapper, source.read_bytes(), 0o755, {"file": str(wrapper), "action": "install/update wrapper"})
        existing = servers.get(server_id)
        if server_id in servers and not isinstance(existing, dict):
            raise ValueError("Target MCP entry must be an object.")
        preserved = existing.get("args", []) if existing is not None else []
        if isinstance(preserved, list) and preserved and (
                (isinstance(preserved[0], str) and not preserved[0].startswith("--"))
                or any(isinstance(arg, str) and (arg in ("-y", "dlx") or "@playwright/mcp" in arg)
                       for arg in preserved)):
            argument_warnings.append(
                server_id + ": preserved args look launcher-style; they would be passed to the "
                "MCP server, not its launcher. Consider removing them before using the wrapper.")
        entry = (copy.deepcopy(existing) if existing is not None
                 else {"args": args, "type": "stdio", "tools": ["*"]})
        entry["command"] = str(wrapper)
        if existing != entry:
            preserved = entry.get("args", [])
            changes.append({"server": server_id, "action": "add/update command",
                            "args": ("<%d args preserved>" % (
                                len(preserved) if isinstance(preserved, list) else 0)
                                if existing is not None else args)})
        servers[server_id] = entry
    install(docker_path, encoded(docker), 0o600, {"file": str(docker_path), "action": "configure browser (endpoint redacted)"})
    mcp_mode = stat.S_IMODE(mcp_config.stat().st_mode) if mcp_config.exists() else 0o600
    # Entry changes are displayed separately; the digest covers the whole preserved file.
    before = len(changes)
    install(mcp_config, encoded(mcp), mcp_mode, {"file": str(mcp_config), "action": "write MCP config"})
    if len(changes) > before and any("server" in change for change in changes[:before]):
        changes.pop()
    canonical = [[str(path), hashlib.sha256(data).hexdigest(), mode] for path, data, mode in writes]
    digest = hashlib.sha256(encoded([canonical, states, bin_dir.exists()], canonical=True)).hexdigest()
    warnings = argument_warnings + [
        image_warning(home),
        "Docker browser is headless with no login state; use the headed server with sandbox OFF for logged-in flows.",
        "Docker socket gives near-unsandboxed host access.",
        "The run-server endpoint is protected only by an unguessable path on 127.0.0.1; local processes that can read docker.json can drive the browser.",
        "exposeNetwork <loopback> lets the browser reach host loopback services; credential masking ON blocks loopback.",
        "Container startup fetches playwright@" + PW_VERSION + " via npx: pinned version, but supply-chain risk remains. PW_IMAGE allows digest pinning.",
    ]
    if not bin_dir.exists():
        warnings.append("bin-dir is new: rerun /app-sandbox-setup plan/apply for its readonly grant, then restart sessions and verify wrapper readability in the sandbox.")
    else:
        warnings.append("Verify bin-dir and wrapper readability in a NEW sandboxed session; this helper does not read data.db.")
    return {"changes": changes, "warnings": warnings, "digest": digest}, writes


def atomic_write(path, data, mode):
    check_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        check_path(path)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main(argv=None):
    parser = SafeParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "apply"))
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--mcp-config", type=Path)
    parser.add_argument("--bin-dir", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--confirm")
    try:
        args = parser.parse_args(argv)
    except UsageError:
        print("Invalid usage; see --help.")
        return 1
    home = args.home.resolve()
    mcp_config = Path(os.path.abspath(args.mcp_config or home / ".copilot/mcp-config.json"))
    bin_dir = Path(os.path.abspath(args.bin_dir or home / ".local/bin"))
    if args.command == "apply" and not args.confirm:
        print("apply requires --confirm DIGEST.")
        return 1
    try:
        plan, writes = build_plan(home, mcp_config, bin_dir)
        if args.command == "apply":
            if args.confirm != plan["digest"]:
                print("Digest mismatch; run plan again and reconfirm.")
                return 4
            copilot = home / ".copilot"
            needs_backup = mcp_config.exists() and any(path == mcp_config for path, _, _ in writes)
            if needs_backup or any(path == copilot or copilot in path.parents for path, _, _ in writes):
                check_path(copilot, directory=True)
                copilot.mkdir(mode=0o700, exist_ok=True)
            if needs_backup:
                directory = home / ".copilot/app-sandbox-setup-backups"
                directory.mkdir(parents=True, exist_ok=True, mode=0o700)
                directory.chmod(0o700)
                timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
                original, _ = read_regular(mcp_config)
                if original is None:
                    raise OSError("MCP config disappeared.")
                atomic_write(directory / ("mcp-config.json." + timestamp), original, 0o600)
            for path, data, mode in writes:
                if path == home / ".config/playwright-mcp/docker.json":
                    config = json.loads(data)
                    if config["browser"]["remoteEndpoint"]["endpoint"] == NEW_ENDPOINT:
                        config["browser"]["remoteEndpoint"]["endpoint"] = (
                            "ws://127.0.0.1:53333/" + secrets.token_urlsafe(32))
                    data = encoded(config)
                atomic_write(path, data, mode)
            print("Applied. Verify wrapper readability in a new sandboxed session.")
        elif args.json:
            print(json.dumps(plan, ensure_ascii=True, sort_keys=True))
        else:
            for change in plan["changes"]:
                print(json.dumps(change, ensure_ascii=True))
            if not writes:
                print("No changes.")
            for warning in plan["warnings"]:
                print("Warning: " + warning)
            print("Plan digest: " + plan["digest"])
        return 0
    except (ValueError, json.JSONDecodeError):
        print("Invalid JSON or object structure; nothing written.")
        return 3
    except OSError:
        print("Setup failed: check path types and access permissions. Writes are atomic per file; "
              "if apply was interrupted, rerun plan to review remaining changes.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
