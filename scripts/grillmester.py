#!/usr/bin/env python3
"""Launch a reviewed Grillmester client through cplt."""

from __future__ import annotations

import argparse
import datetime as dt
import errno
import importlib.util
import json
import os
import re
import selectors
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence


SUPPORTED_CPLT_RELEASE = "2026.08.17-062831-1008a92"
MINIMUM_OPENCODE_VERSION_TEXT = "1.18.20"
MINIMUM_OPENCODE_VERSION = tuple(
    int(part) for part in MINIMUM_OPENCODE_VERSION_TEXT.split(".")
)
SUPPORTED_OPENCODE_MAJOR = MINIMUM_OPENCODE_VERSION[0]
MINIMUM_COPILOT_VERSION = (1, 0, 79)
SUPPORTED_COPILOT_MAJOR = MINIMUM_COPILOT_VERSION[0]
CLIENTS = ("copilot", "opencode")
PUBLIC_AGENTS = ("grillmester", "barista", "designer", "doctor-who")
OPENCODE_COMMANDS = frozenset(
    {
        "acp",
        "agent",
        "attach",
        "auth",
        "completion",
        "db",
        "debug",
        "export",
        "github",
        "import",
        "mcp",
        "models",
        "plugin",
        "plug",
        "pr",
        "providers",
        "run",
        "serve",
        "session",
        "stats",
        "uninstall",
        "upgrade",
        "web",
    }
)
CPLT_SUBCOMMANDS = frozenset(
    {
        "check",
        "config",
        "doctor",
        "exec",
        "help",
        "init",
        "settings",
        "trust",
        "update",
        "update-lists",
    }
)
SEMVER_PATTERN = (
    r"(?P<major>0|[1-9]\d*)\."
    r"(?P<minor>0|[1-9]\d*)\."
    r"(?P<patch>0|[1-9]\d*)"
    r"(?P<prerelease>-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
)
OPENCODE_VERSION_PATTERN = re.compile(
    rf"^(?:OpenCode(?: version)? )?{SEMVER_PATTERN}$",
    re.IGNORECASE,
)
COPILOT_VERSION_PATTERN = re.compile(
    rf"^(?:GitHub Copilot CLI(?: version)? )?{SEMVER_PATTERN}\.?$",
    re.IGNORECASE,
)
COPILOT_UPDATE_HINT = "Run 'copilot update' to check for updates."
CPLT_VERSION_PATTERN = re.compile(
    r"^cplt (?P<release>(?P<stamp>\d{4}\.\d{2}\.\d{2}-\d{6})-[0-9a-f]{7,40})$"
)
MINIMUM_CPLT_STAMP = dt.datetime.strptime(
    SUPPORTED_CPLT_RELEASE.rsplit("-", 1)[0], "%Y.%m.%d-%H%M%S"
)
PREFERENCE_FILE = "preferences.json"
PREFERENCE_SCHEMA_VERSION = 1
OPENCODE_RUNTIME_GITIGNORE = (
    b"node_modules\npackage.json\npackage-lock.json\nbun.lock\n.gitignore\n"
)
AGENT_LABELS = {
    "grillmester": "Grillmester – uklare, viktige eller tverrgående oppgaver",
    "barista": "Barista – tydelige utviklingsoppgaver",
    "designer": "Designer – design, prototyper og brukerflyt",
    "doctor-who": "Doctor Who – discovery, produkt og arkitektur",
}
CLIENT_LABELS = {
    "copilot": "GitHub Copilot CLI",
    "opencode": "OpenCode",
}
LAUNCHER_LONG_OPTIONS = (
    "--agent",
    "--client",
    "--print-command",
    "--project-dir",
    "--role",
)


class LauncherError(RuntimeError):
    """Raised when a safe, supported launch cannot be constructed."""


class InvalidPreferencesError(LauncherError):
    """Raised when a regular preferences file has replaceable content errors."""


class MissingBinaryError(LauncherError):
    """Raised when one required executable cannot be resolved on PATH."""


@dataclass(frozen=True)
class Invocation:
    client: str
    agent: str
    project_dir: Path
    cplt_args: tuple[str, ...]
    client_args: tuple[str, ...]
    print_command: bool


@dataclass(frozen=True)
class Distribution:
    root: Path
    plugin: Path
    opencode_target: Path
    focused_opencode_target: Path
    focused_copilot_target: Path
    version: str


@dataclass(frozen=True)
class Preferences:
    client: str
    agent: str


@dataclass(frozen=True)
class CheckedBinary:
    label: str
    path: str
    version: str | None = None

    @property
    def detail(self) -> str:
        if self.version is None:
            return self.path
        return f"{self.path} ({self.version})"


@dataclass(frozen=True)
class LaunchChecks:
    cplt: CheckedBinary
    client: CheckedBinary


def distribution_root() -> Path:
    """Resolve through a Homebrew/bin symlink to the immutable bundle root."""

    return Path(__file__).resolve(strict=True).parent.parent


def _read_json_object(
    path: Path,
    *,
    label: str,
    content_error: Callable[[str], LauncherError] = LauncherError,
) -> dict[str, object]:
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise LauncherError(f"could not read {label} at {path}: {exc}") from exc
    if len(content) > 2 * 1024 * 1024:
        raise content_error(f"{label} exceeds the 2 MiB safety limit: {path}")
    try:
        value = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise content_error(f"{label} is not valid UTF-8 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise content_error(f"{label} must be a JSON object: {path}")
    return value


def load_distribution(root: Path | None = None) -> Distribution:
    root = (root or distribution_root()).resolve(strict=True)
    plugin = root / "plugin"
    target = root / "targets/opencode-v1"
    focused_opencode = root / "targets/opencode-v1-focused"
    focused_copilot = root / "targets/copilot-cli-focused-v1"
    if not plugin.is_dir() or plugin.is_symlink():
        raise LauncherError(f"distribution has no regular plugin directory: {plugin}")
    if not target.is_dir() or target.is_symlink():
        raise LauncherError(f"distribution has no regular OpenCode target: {target}")
    for path, label in (
        (focused_opencode, "focused OpenCode target"),
        (focused_copilot, "focused Copilot CLI target"),
    ):
        if not path.is_dir() or path.is_symlink():
            raise LauncherError(f"distribution has no regular {label}: {path}")

    plugin_manifest = _read_json_object(
        plugin / "plugin.json", label="Copilot plugin manifest"
    )
    if plugin_manifest.get("name") != "grillmester":
        raise LauncherError("Copilot plugin manifest does not name grillmester")
    version = plugin_manifest.get("version")
    if not isinstance(version, str) or not version.strip():
        raise LauncherError("Copilot plugin manifest has no version")

    target_manifest = _read_json_object(
        target / "manifest.json", label="OpenCode target manifest"
    )
    if target_manifest.get("target") != "opencode-v1":
        raise LauncherError("OpenCode target manifest does not name opencode-v1")
    counts = target_manifest.get("counts")
    if not isinstance(counts, dict) or counts.get("agents") != 7 or counts.get(
        "skills"
    ) != 42:
        raise LauncherError("OpenCode target manifest does not contain 7 agents and 42 skills")
    focused_contracts = (
        (
            focused_opencode / "manifest.json",
            "focused OpenCode target manifest",
            "opencode-v1-focused",
            {"agents": 2, "skills": 7, "commands": 7},
        ),
        (
            focused_copilot / "manifest.json",
            "focused Copilot CLI target manifest",
            "copilot-cli-focused-v1",
            {"agents": 2, "skills": 7},
        ),
    )
    for manifest_path, label, expected_target, expected_counts in focused_contracts:
        manifest = _read_json_object(manifest_path, label=label)
        if (
            manifest.get("schemaVersion") != 1
            or manifest.get("target") != expected_target
            or manifest.get("projection") != "focused-context-v1"
            or manifest.get("counts") != expected_counts
            or manifest.get("agents") != ["barista", "grill-inspektor"]
        ):
            raise LauncherError(f"{label} differs from the reviewed focused contract")
    return Distribution(
        root,
        plugin,
        target,
        focused_opencode,
        focused_copilot,
        version,
    )


def _load_local_mode_module() -> object:
    """Load the bundled sibling deliberately under Python isolated mode."""

    cached = sys.modules.get("_grillmester_bundled_local_mode")
    if cached is not None:
        return cached
    path = Path(__file__).resolve(strict=True).with_name("grillmester_local.py")
    try:
        observed = path.lstat()
    except OSError as exc:
        raise LauncherError(f"could not inspect bundled local launcher {path}: {exc}") from exc
    if stat.S_ISLNK(observed.st_mode) or not stat.S_ISREG(observed.st_mode):
        raise LauncherError(f"bundled local launcher must be a regular file: {path}")
    module_name = "_grillmester_bundled_local_mode"
    specification = importlib.util.spec_from_file_location(module_name, path)
    if specification is None or specification.loader is None:
        raise LauncherError(f"could not create a loader for bundled local launcher: {path}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[module_name] = module
    try:
        specification.loader.exec_module(module)
    except Exception as exc:
        sys.modules.pop(module_name, None)
        raise LauncherError(f"could not load bundled local launcher: {exc}") from exc
    return module


def config_home(environment: Mapping[str, str] | None = None) -> Path:
    environment = os.environ if environment is None else environment
    configured = environment.get("XDG_CONFIG_HOME")
    if configured:
        root = Path(configured).expanduser()
        if not root.is_absolute():
            raise LauncherError("XDG_CONFIG_HOME must be an absolute path")
    else:
        root = Path.home() / ".config"
    return root


def preference_path(environment: Mapping[str, str] | None = None) -> Path:
    return config_home(environment) / "grillmester" / PREFERENCE_FILE


def load_preferences(path: Path | None = None) -> Preferences | None:
    path = path or preference_path()

    def invalid(message: str) -> InvalidPreferencesError:
        return InvalidPreferencesError(
            f"{message}. Run 'grillmester choose' to replace the saved default "
            f"or remove {path}"
        )

    try:
        observed = path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise LauncherError(f"could not inspect preferences at {path}: {exc}") from exc
    if stat.S_ISLNK(observed.st_mode) or not stat.S_ISREG(observed.st_mode):
        raise LauncherError(f"preferences must be a regular, non-symlink file: {path}")
    value = _read_json_object(
        path, label="Grillmester preferences", content_error=invalid
    )
    if set(value) != {"schemaVersion", "client", "agent"}:
        raise invalid("Grillmester preferences have unexpected or missing fields")
    if value.get("schemaVersion") != PREFERENCE_SCHEMA_VERSION:
        raise invalid("Grillmester preferences use an unsupported schema")
    client = value.get("client")
    agent = value.get("agent")
    if client not in CLIENTS or agent not in PUBLIC_AGENTS:
        raise invalid("Grillmester preferences contain an unsupported client or agent")
    assert isinstance(client, str) and isinstance(agent, str)
    return Preferences(client, agent)


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def save_preferences(preferences: Preferences, path: Path | None = None) -> Path:
    if preferences.client not in CLIENTS or preferences.agent not in PUBLIC_AGENTS:
        raise LauncherError("cannot save an unsupported client or agent")
    path = path or preference_path()
    parent = path.parent
    try:
        parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        parent_stat = parent.lstat()
    except OSError as exc:
        raise LauncherError(f"could not prepare preferences directory {parent}: {exc}") from exc
    if stat.S_ISLNK(parent_stat.st_mode) or not stat.S_ISDIR(parent_stat.st_mode):
        raise LauncherError(f"preferences parent must be a regular directory: {parent}")
    try:
        os.chmod(parent, 0o700)
    except OSError as exc:
        raise LauncherError(f"could not protect preferences directory {parent}: {exc}") from exc
    content = (
        json.dumps(
            {
                "schemaVersion": PREFERENCE_SCHEMA_VERSION,
                "client": preferences.client,
                "agent": preferences.agent,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    descriptor = -1
    temporary_name = ""
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=parent
        )
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            descriptor = -1
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists() or path.is_symlink():
            current = path.lstat()
            if stat.S_ISLNK(current.st_mode) or not stat.S_ISREG(current.st_mode):
                raise LauncherError(
                    f"refusing to replace non-regular preferences file: {path}"
                )
        os.replace(temporary_name, path)
        temporary_name = ""
        _fsync_directory(parent)
    except LauncherError:
        raise
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise LauncherError(f"refusing symlinked preferences path: {path}") from exc
        raise LauncherError(f"could not save preferences at {path}: {exc}") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_name:
            try:
                Path(temporary_name).unlink(missing_ok=True)
            except OSError:
                pass
    return path


def ensure_opencode_runtime_support(
    distribution: Distribution,
    environment: Mapping[str, str] | None = None,
) -> Path:
    """Pre-seed OpenCode's two write-if-absent config markers for cplt."""

    bundled = distribution.opencode_target / ".gitignore"
    try:
        bundled_stat = bundled.lstat()
        bundled_content = bundled.read_bytes()
    except OSError as exc:
        raise LauncherError(
            f"could not inspect distributed OpenCode runtime support: {exc}"
        ) from exc
    if stat.S_ISLNK(bundled_stat.st_mode) or not stat.S_ISREG(bundled_stat.st_mode):
        raise LauncherError(
            f"distributed OpenCode runtime support must be a regular file: {bundled}"
        )
    if bundled_content != OPENCODE_RUNTIME_GITIGNORE:
        raise LauncherError("distributed OpenCode runtime support content differs")

    support = config_home(environment) / "opencode/.gitignore"
    try:
        observed = support.lstat()
    except FileNotFoundError:
        observed = None
    except OSError as exc:
        raise LauncherError(
            f"could not inspect OpenCode runtime support at {support}: {exc}"
        ) from exc
    if observed is None:
        parent = support.parent
        try:
            parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            parent_stat = parent.lstat()
        except OSError as exc:
            raise LauncherError(
                f"could not prepare OpenCode config directory {parent}: {exc}"
            ) from exc
        if stat.S_ISLNK(parent_stat.st_mode) or not stat.S_ISDIR(parent_stat.st_mode):
            raise LauncherError(
                f"OpenCode config parent must be a regular directory: {parent}"
            )
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(support, flags, 0o600)
        except FileExistsError:
            descriptor = -1
        except OSError as exc:
            raise LauncherError(
                f"could not create OpenCode runtime support at {support}: {exc}"
            ) from exc
        if descriptor >= 0:
            created = True
            try:
                with os.fdopen(descriptor, "wb", closefd=True) as output:
                    descriptor = -1
                    output.write(OPENCODE_RUNTIME_GITIGNORE)
                    output.flush()
                    os.fsync(output.fileno())
                _fsync_directory(parent)
            except OSError as exc:
                if created:
                    try:
                        support.unlink(missing_ok=True)
                    except OSError:
                        pass
                raise LauncherError(
                    f"could not write OpenCode runtime support at {support}: {exc}"
                ) from exc
            finally:
                if descriptor >= 0:
                    os.close(descriptor)
        try:
            observed = support.lstat()
        except OSError as exc:
            raise LauncherError(
                f"could not verify OpenCode runtime support at {support}: {exc}"
            ) from exc
    if stat.S_ISLNK(observed.st_mode) or not stat.S_ISREG(observed.st_mode):
        raise LauncherError(
            f"OpenCode runtime support must be a regular, non-symlink file: {support}"
        )
    return support


def _split_separator(arguments: Sequence[str]) -> tuple[list[str], list[str]]:
    try:
        separator = arguments.index("--")
    except ValueError:
        return list(arguments), []
    return list(arguments[:separator]), list(arguments[separator + 1 :])


def parse_invocation(
    arguments: Sequence[str],
    *,
    cwd: Path | None = None,
    defaults: Preferences | None = None,
) -> Invocation:
    wrapper, client_args = _split_separator(arguments)
    parser = argparse.ArgumentParser(
        prog="grillmester",
        allow_abbrev=False,
        description="Launch Grillmester in Copilot CLI or OpenCode through cplt.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Commands:\n"
            "  choose    change and save the default without launching\n"
            "  doctor    verify the distribution and installed clients\n"
            "  local     use one configured loopback model (focused by default)\n"
            "  update    update the Homebrew installation\n"
            "  help      show this help\n"
            "  version   show the installed Grillmester version\n\n"
            "Examples:\n"
            "  grillmester\n"
            "  grillmester doctor --client opencode\n"
            "  grillmester --client opencode --agent barista\n"
            "  grillmester local setup\n"
            "  grillmester local\n"
            "  grillmester local --full\n"
            "  grillmester --client copilot --agent designer --print-command\n\n"
            "Arguments unknown to Grillmester are forwarded to cplt. Arguments "
            "after -- go to the selected client."
        ),
    )
    client_name = wrapper.pop(0) if wrapper[:1] and wrapper[0] in CLIENTS else None
    parser.add_argument(
        "--client", choices=CLIENTS, help="terminal client to start through cplt"
    )
    parser.add_argument(
        "--agent",
        "--role",
        dest="agent",
        choices=PUBLIC_AGENTS,
        help="public Grillmester agent (--role remains a compatible alias)",
    )
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=cwd or Path.cwd(),
        help="consumer repository for the sandbox (default: current directory)",
    )
    parser.add_argument(
        "--print-command",
        action="store_true",
        help="print the exact cplt command without starting a client",
    )
    options, cplt_args = parser.parse_known_args(wrapper)
    if options.client and client_name and options.client != client_name:
        parser.error("positional client and --client disagree")
    client = options.client or client_name or (
        defaults.client if defaults is not None else "copilot"
    )
    agent = options.agent or (
        defaults.agent if defaults is not None else "grillmester"
    )
    project_dir = options.project_dir.expanduser().resolve(strict=True)
    if not project_dir.is_dir():
        parser.error(f"project directory is not a directory: {project_dir}")
    _reject_reserved_arguments(cplt_args, client_args, client=client)
    return Invocation(
        client=client,
        agent=agent,
        project_dir=project_dir,
        cplt_args=tuple(cplt_args),
        client_args=tuple(client_args),
        print_command=options.print_command,
    )


def _contains_option(arguments: Sequence[str], option: str) -> bool:
    return any(value == option or value.startswith(option + "=") for value in arguments)


def _contains_short_option(arguments: Sequence[str], option: str) -> bool:
    return any(value == option or value.startswith(option) for value in arguments)


def _reject_reserved_arguments(
    cplt_args: Sequence[str], client_args: Sequence[str], *, client: str
) -> None:
    if _contains_option(cplt_args, "--no-audit"):
        raise LauncherError(
            "cplt --no-audit is already enforced by Grillmester; remove it"
        )
    for option in ("--agent", "--project-dir"):
        if _contains_option(cplt_args, option):
            raise LauncherError(
                f"{option} is owned by Grillmester; use --client, --agent or "
                "--project-dir before --"
            )
    if _contains_short_option(cplt_args, "-d"):
        raise LauncherError(
            "cplt -d is owned by Grillmester; use --project-dir before --"
        )
    subcommands = CPLT_SUBCOMMANDS.intersection(cplt_args)
    if subcommands:
        raise LauncherError(
            "cplt subcommands are not launch arguments: "
            + ", ".join(sorted(subcommands))
        )
    if _contains_option(client_args, "--agent"):
        raise LauncherError(
            "client --agent is owned by Grillmester; put --agent before --"
        )
    if _contains_option(client_args, "--project-dir"):
        raise LauncherError(
            "client --project-dir is owned by Grillmester; put it before --"
        )
    if client == "copilot" and _contains_option(client_args, "--plugin-dir"):
        raise LauncherError(
            "Copilot --plugin-dir is owned by Grillmester's reviewed distribution"
        )


def build_launch_command(
    invocation: Invocation,
    distribution: Distribution,
    *,
    cplt: str = "cplt",
) -> tuple[list[str], dict[str, str]]:
    payload = (
        distribution.plugin
        if invocation.client == "copilot"
        else distribution.opencode_target
    )
    command = [
        cplt,
        # cplt's current parent-side audit may execute repository-configured
        # Git helpers outside the sandbox. Disable it until upstream runs the
        # audit with repository config, hooks and fsmonitor disabled.
        "--no-audit",
        "--agent",
        invocation.client,
        "--project-dir",
        str(invocation.project_dir),
        "--allow-read",
        str(payload),
    ]
    environment = dict(os.environ)
    if invocation.client == "opencode":
        environment["OPENCODE_CONFIG_DIR"] = str(distribution.opencode_target)
        command.extend(("--pass-env", "OPENCODE_CONFIG_DIR"))
        client_arguments = _opencode_client_arguments(
            invocation.agent, invocation.client_args
        )
    else:
        client_arguments = [
            "--plugin-dir",
            str(distribution.plugin),
            "--agent",
            f"grillmester:{invocation.agent}",
            *invocation.client_args,
        ]
    command.extend(invocation.cplt_args)
    command.append("--")
    command.extend(client_arguments)
    return command, environment


def _opencode_client_arguments(
    agent: str, arguments: Sequence[str]
) -> list[str]:
    """Bind agents only to OpenCode session entry points that accept them."""

    forwarded = list(arguments)
    if not forwarded:
        return ["--agent", agent]
    if forwarded[0] == "run":
        return ["run", "--agent", agent, *forwarded[1:]]
    if forwarded[0] in OPENCODE_COMMANDS:
        return forwarded
    return ["--agent", agent, *forwarded]


CLIENT_INSTALL_HINTS = {
    "copilot": "brew install --cask copilot-cli",
    "cplt": "brew install navikt/tap/cplt",
    "opencode": "brew install opencode",
}


def _resolve_binary(name: str) -> str:
    resolved = shutil.which(name)
    if resolved is None:
        install = CLIENT_INSTALL_HINTS.get(name, f"brew install {name}")
        label = {
            "copilot": "GitHub Copilot CLI",
            "cplt": "cplt",
            "opencode": "OpenCode",
        }.get(name, name)
        raise MissingBinaryError(
            f"{label} was not found on PATH; install it with: {install}"
        )
    return str(Path(resolved).resolve(strict=True))


def _trusted_cplt_version_output(
    binary: str, *, environment: Mapping[str, str] | None = None
) -> str:
    """Inspect the required sandbox binary before it becomes the trust boundary."""

    try:
        result = subprocess.run(
            [binary, "--version"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=8,
            check=False,
            env=None if environment is None else dict(environment),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LauncherError(f"could not inspect {binary}: {exc}") from exc
    output = result.stdout.strip()
    if result.returncode != 0 or not output:
        raise LauncherError(f"{binary} --version failed with exit {result.returncode}")
    return output.splitlines()[0].strip()


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
        return
    except OSError:
        pass
    if process.poll() is None:
        try:
            process.kill()
        except OSError:
            pass


def _bounded_command_output(
    command: Sequence[str],
    *,
    environment: Mapping[str, str],
    timeout: float = 30,
    max_output_bytes: int = 64 * 1024,
) -> tuple[int, str, str]:
    """Run one sandbox probe with bounded output and whole-group timeout cleanup."""

    try:
        process = subprocess.Popen(
            list(command),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=dict(environment),
            start_new_session=True,
        )
    except OSError as exc:
        raise LauncherError(f"could not start sandboxed client probe: {exc}") from exc
    assert process.stdout is not None and process.stderr is not None
    selector = selectors.DefaultSelector()
    streams = {
        process.stdout: bytearray(),
        process.stderr: bytearray(),
    }
    selector.register(process.stdout, selectors.EVENT_READ)
    selector.register(process.stderr, selectors.EVENT_READ)
    deadline = time.monotonic() + timeout
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _terminate_process_group(process)
                process.wait()
                raise LauncherError(
                    f"sandboxed client version probe timed out after {timeout:g} seconds"
                )
            events = selector.select(remaining)
            if not events:
                continue
            for key, _ in events:
                stream = key.fileobj
                chunk = os.read(stream.fileno(), 8192)
                if not chunk:
                    selector.unregister(stream)
                    stream.close()
                    continue
                streams[stream].extend(chunk)
                total = sum(len(buffer) for buffer in streams.values())
                if total > max_output_bytes:
                    _terminate_process_group(process)
                    process.wait()
                    raise LauncherError(
                        "sandboxed client version probe exceeded the "
                        f"{max_output_bytes}-byte output limit"
                    )
        try:
            returncode = process.wait(timeout=max(0.0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            _terminate_process_group(process)
            process.wait()
            raise LauncherError(
                f"sandboxed client version probe timed out after {timeout:g} seconds"
            ) from None
    finally:
        selector.close()
        _terminate_process_group(process)
        if process.poll() is None:
            process.wait()
        for stream in streams:
            if not stream.closed:
                stream.close()

    try:
        stdout = bytes(streams[process.stdout]).decode("utf-8")
        stderr = bytes(streams[process.stderr]).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LauncherError(
            "sandboxed client version probe did not return UTF-8 output"
        ) from exc
    return returncode, stdout, stderr


def _client_probe(
    client: str,
    *,
    cplt: CheckedBinary,
    distribution: Distribution,
    probe_dir: Path,
    environment: Mapping[str, str] | None = None,
    cplt_arguments: Sequence[str] = (),
) -> tuple[list[str], dict[str, str]]:
    invocation = Invocation(
        client=client,
        agent="grillmester",
        project_dir=probe_dir.resolve(strict=True),
        cplt_args=(),
        client_args=("--version",),
        print_command=False,
    )
    command, launch_environment = build_launch_command(
        invocation, distribution, cplt=cplt.path
    )
    if environment is not None:
        launch_environment = dict(environment)
        if client == "opencode":
            launch_environment.setdefault(
                "OPENCODE_CONFIG_DIR", str(distribution.opencode_target)
            )
    if cplt_arguments:
        separator = command.index("--")
        command[separator:separator] = list(cplt_arguments)
    command[1:1] = ["--yes", "--quiet"]
    return command, launch_environment


def _sandboxed_client_version(
    client: str,
    *,
    cplt: CheckedBinary,
    distribution: Distribution,
    environment: Mapping[str, str] | None = None,
    cplt_arguments: Sequence[str] = (),
) -> str:
    with tempfile.TemporaryDirectory(prefix="grillmester-client-probe-") as directory:
        probe_dir = Path(directory)
        probe_dir.chmod(0o700)
        command, environment = _client_probe(
            client,
            cplt=cplt,
            distribution=distribution,
            probe_dir=probe_dir,
            environment=environment,
            cplt_arguments=cplt_arguments,
        )
        returncode, stdout, stderr = _bounded_command_output(
            command,
            environment=environment,
        )
    return _strict_client_version_output(client, returncode, stdout, stderr)


def _strict_client_version_output(
    client: str, returncode: int, stdout: str, stderr: str
) -> str:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if returncode != 0:
        diagnostic = " ".join(stderr.split())[:500]
        suffix = f": {diagnostic}" if diagnostic else ""
        raise LauncherError(
            f"sandboxed {CLIENT_LABELS[client]} version probe failed with "
            f"exit {returncode}{suffix}"
        )
    if client == "copilot":
        version_lines = [line for line in lines if COPILOT_VERSION_PATTERN.fullmatch(line)]
        unexpected = [
            line
            for line in lines
            if line not in version_lines and line != COPILOT_UPDATE_HINT
        ]
        if len(version_lines) == 1 and not unexpected and lines.count(COPILOT_UPDATE_HINT) <= 1:
            return version_lines[0]
    elif len(lines) == 1:
        return lines[0]
    if len(lines) != 1:
        raise LauncherError(
            f"sandboxed {CLIENT_LABELS[client]} version probe returned "
            f"unexpected stdout; expected one strict version line"
        )
    raise LauncherError(
        f"sandboxed {CLIENT_LABELS[client]} version probe returned an "
        "unexpected stdout line"
    )


def _semantic_version(
    output: str,
    *,
    label: str,
    pattern: re.Pattern[str],
) -> tuple[int, int, int]:
    match = pattern.fullmatch(output)
    if match is None:
        raise LauncherError(f"could not parse {label} version from {output!r}")
    if match.group("prerelease") is not None:
        raise LauncherError(
            f"{label} prerelease versions are not supported; found {output!r}"
        )
    return tuple(
        int(match.group(name)) for name in ("major", "minor", "patch")
    )  # type: ignore[return-value]


def _opencode_semver(output: str) -> tuple[int, int, int]:
    return _semantic_version(
        output,
        label="OpenCode",
        pattern=OPENCODE_VERSION_PATTERN,
    )


def _copilot_semver(output: str) -> tuple[int, int, int]:
    return _semantic_version(
        output,
        label="Copilot CLI",
        pattern=COPILOT_VERSION_PATTERN,
    )


def _cplt_release(output: str) -> tuple[str, dt.datetime]:
    match = CPLT_VERSION_PATTERN.fullmatch(output)
    if match is None:
        raise LauncherError(f"could not parse cplt version from {output!r}")
    try:
        stamp = dt.datetime.strptime(match.group("stamp"), "%Y.%m.%d-%H%M%S")
    except ValueError as exc:
        raise LauncherError(f"could not parse cplt version from {output!r}") from exc
    return match.group("release"), stamp


def check_cplt(
    *,
    binary: str | None = None,
    environment: Mapping[str, str] | None = None,
) -> CheckedBinary:
    cplt = _resolve_binary("cplt") if binary is None else binary
    cplt_version = (
        _trusted_cplt_version_output(cplt)
        if environment is None
        else _trusted_cplt_version_output(cplt, environment=environment)
    )
    release, stamp = _cplt_release(cplt_version)
    if release != SUPPORTED_CPLT_RELEASE and stamp <= MINIMUM_CPLT_STAMP:
        raise LauncherError(
            "cplt must be the tested baseline "
            f"{SUPPORTED_CPLT_RELEASE} or a newer release; found {cplt_version!r}"
        )
    return CheckedBinary("cplt", cplt, cplt_version)


def check_client_runtime(
    client: str,
    *,
    cplt: CheckedBinary | None = None,
    distribution: Distribution | None = None,
    binary: str | None = None,
    probe_environment: Mapping[str, str] | None = None,
    probe_cplt_arguments: Sequence[str] = (),
) -> CheckedBinary:
    binary = _resolve_binary(client) if binary is None else binary
    cplt = check_cplt() if cplt is None else cplt
    distribution = load_distribution() if distribution is None else distribution
    version = _sandboxed_client_version(
        client,
        cplt=cplt,
        distribution=distribution,
        environment=probe_environment,
        cplt_arguments=probe_cplt_arguments,
    )
    if client == "opencode":
        observed = _opencode_semver(version)
        if (
            observed < MINIMUM_OPENCODE_VERSION
            or observed[0] != SUPPORTED_OPENCODE_MAJOR
        ):
            raise LauncherError(
                "OpenCode must be in the supported 1.x range, starting at "
                f"{MINIMUM_OPENCODE_VERSION_TEXT}; found {version!r}"
            )
    else:
        observed = _copilot_semver(version)
        if (
            observed < MINIMUM_COPILOT_VERSION
            or observed[0] != SUPPORTED_COPILOT_MAJOR
        ):
            minimum = ".".join(str(part) for part in MINIMUM_COPILOT_VERSION)
            raise LauncherError(
                "Copilot CLI must be in the supported 1.x range, starting at "
                f"{minimum}; found {version!r}"
            )
    return CheckedBinary(client, binary, version)


def check_client(
    client: str,
    *,
    distribution: Distribution | None = None,
) -> LaunchChecks:
    distribution = load_distribution() if distribution is None else distribution
    cplt = check_cplt()
    runtime = check_client_runtime(
        client,
        cplt=cplt,
        distribution=distribution,
    )
    return LaunchChecks(cplt, runtime)


def discover_clients(candidates: Sequence[str] = CLIENTS) -> tuple[str, ...]:
    """Find PATH clients without executing any ambient client binary."""

    available: list[str] = []
    for client in candidates:
        try:
            _resolve_binary(client)
        except MissingBinaryError as exc:
            print(f"Ikke tilgjengelig: {exc}")
            continue
        available.append(client)
    if not available:
        raise LauncherError(
            "no supported terminal client was found on PATH; install OpenCode "
            "with 'brew install opencode' or GitHub Copilot CLI with "
            "'brew install --cask copilot-cli'"
        )
    return tuple(available)


def _homebrew_managed_installation() -> bool:
    """Report whether this launcher runs from a Homebrew keg."""

    try:
        script = Path(__file__).resolve(strict=True)
    except OSError:
        return False
    if "Cellar" in script.parts:
        return True
    cellar = os.environ.get("HOMEBREW_CELLAR")
    if not cellar:
        return False
    try:
        return script.is_relative_to(Path(cellar).resolve())
    except OSError:
        return False


def update_installation() -> None:
    """Refresh Homebrew metadata and replace this installation explicitly."""

    if not _homebrew_managed_installation():
        raise LauncherError(
            "this Grillmester does not run from a Homebrew installation, so "
            "'grillmester update' would not update it; update the checkout or "
            "distribution through its own channel instead"
        )
    resolved = shutil.which("brew")
    if resolved is None:
        raise LauncherError(
            "Homebrew was not found on PATH; install it from https://brew.sh/"
        )
    try:
        brew = str(Path(resolved).resolve(strict=True))
        refreshed = subprocess.run([brew, "update"], check=False)
    except OSError as exc:
        raise LauncherError(f"could not run Homebrew update: {exc}") from exc
    if refreshed.returncode != 0:
        raise LauncherError(
            f"brew update failed with exit {refreshed.returncode}; "
            "Grillmester was not upgraded"
        )
    os.execv(brew, [brew, "upgrade", "grillmester"])


def doctor(client: str | None, *, root: Path | None = None) -> int:
    distribution = load_distribution(root)
    print(f"ok  distribution {distribution.root} (v{distribution.version})")
    print(f"ok  copilot plugin {distribution.plugin}")
    print(f"ok  OpenCode target {distribution.opencode_target}")
    print(f"ok  focused Copilot CLI target {distribution.focused_copilot_target}")
    print(f"ok  focused OpenCode target {distribution.focused_opencode_target}")
    try:
        cplt_check = check_cplt()
    except LauncherError as exc:
        print(f"error  cplt: {exc}", file=sys.stderr)
        return 1
    print(f"ok  {cplt_check.label} {cplt_check.detail}")

    selected = CLIENTS if client is None else (client,)
    failed = False
    available = 0
    for candidate in selected:
        try:
            runtime = check_client_runtime(
                candidate,
                cplt=cplt_check,
                distribution=distribution,
            )
        except MissingBinaryError as exc:
            if client is not None:
                print(f"error  {candidate}: {exc}", file=sys.stderr)
                failed = True
            else:
                print(
                    f"skip  {candidate} not installed (optional; use "
                    f"'grillmester doctor --client {candidate}' to require it)"
                )
            continue
        except LauncherError as exc:
            print(f"error  {candidate}: {exc}", file=sys.stderr)
            failed = True
            continue
        available += 1
        print(f"ok  {runtime.label} {runtime.detail}")
    if client is None and available == 0:
        print("error  no supported terminal client was found on PATH", file=sys.stderr)
        failed = True
    return 1 if failed else 0


def _prompt(text: str) -> str:
    try:
        return input(text)
    except (EOFError, KeyboardInterrupt):
        print()
        raise LauncherError("selection cancelled") from None


def _read_choice(
    title: str,
    values: Sequence[str],
    labels: Mapping[str, str],
    default: str,
) -> str:
    print(title)
    for index, value in enumerate(values, start=1):
        suffix = " (default)" if value == default else ""
        print(f"  {index}. {labels[value]}{suffix}")
    while True:
        answer = _prompt(f"Velg [Enter = {labels[default]}]: ").strip()
        if not answer:
            return default
        if answer.isdigit() and 1 <= int(answer) <= len(values):
            return values[int(answer) - 1]
        if answer in values:
            return answer
        print("Ugyldig valg. Skriv nummeret eller navnet.")


def choose_preferences(
    current: Preferences | None = None,
    *,
    fixed_client: str | None = None,
    fixed_agent: str | None = None,
    available_clients: Sequence[str] | None = None,
    validate: bool = True,
    persist: bool = True,
    validation_cache: dict[str, LaunchChecks] | None = None,
) -> Preferences:
    if persist and not validate:
        raise LauncherError("preferences cannot be saved before client validation")
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise LauncherError(
            "interactive selection requires a terminal; use --client and --agent"
        )
    if available_clients is None:
        if fixed_client is not None:
            _resolve_binary(fixed_client)
            available_clients = (fixed_client,)
        else:
            available_clients = discover_clients()
    if not available_clients or any(
        client not in CLIENTS for client in available_clients
    ):
        raise LauncherError("interactive selection requires a supported client")
    if fixed_client is not None and fixed_client not in available_clients:
        _resolve_binary(fixed_client)
        raise LauncherError(
            f"{CLIENT_LABELS[fixed_client]} is not available for selection"
        )
    default_client = (
        current.client
        if current is not None and current.client in available_clients
        else available_clients[0]
    )
    default_agent = current.agent if current is not None else "grillmester"
    print("\nHva vil du starte?\n")
    if fixed_client is None:
        if len(available_clients) == 1:
            client = available_clients[0]
            print(f"Klient\n  {CLIENT_LABELS[client]} (eneste tilgjengelige)")
        else:
            client = _read_choice(
                "Klient", available_clients, CLIENT_LABELS, default_client
            )
    else:
        client = fixed_client
        print(f"Klient\n  {CLIENT_LABELS[client]} (fra kommandoen)")
    if validate:
        if validation_cache is None:
            check_client_runtime(client)
        else:
            validation_cache[client] = check_client(client)
    print()
    if fixed_agent is None:
        agent = _read_choice("Agent", PUBLIC_AGENTS, AGENT_LABELS, default_agent)
    else:
        agent = fixed_agent
        print(f"Agent\n  {AGENT_LABELS[agent]} (fra kommandoen)")
    preferences = Preferences(client, agent)
    if persist:
        path = save_preferences(preferences)
        print(
            f"\nLagret default: {CLIENT_LABELS[client]} med "
            f"{AGENT_LABELS[agent].split(' – ', 1)[0]}"
        )
        print(f"Preferanser: {path}\n")
    else:
        print("\nValget brukes bare til å vise kommandoen og ble ikke lagret.\n")
    return preferences


def interactive_defaults(
    validation_cache: dict[str, LaunchChecks] | None = None,
) -> Preferences | None:
    current = load_preferences()
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        if current is None:
            raise LauncherError(
                "no saved default in a non-interactive terminal; use --client and --agent"
            )
        return current
    if current is None:
        return choose_preferences(validation_cache=validation_cache)
    prompt = (
        f"Start {CLIENT_LABELS[current.client]} med "
        f"{AGENT_LABELS[current.agent].split(' – ', 1)[0]} gjennom cplt? "
        "[Enter = start, c = endre, q = avslutt]: "
    )
    while True:
        try:
            answer = input(prompt).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if answer in ("", "s", "start"):
            return current
        if answer in ("c", "change", "endre"):
            return choose_preferences(current, validation_cache=validation_cache)
        if answer in ("q", "quit", "avslutt"):
            return None
        print("Ugyldig valg. Trykk Enter, c eller q.")


def _explicit_selection(arguments: Sequence[str]) -> tuple[str | None, str | None]:
    wrapper, _ = _split_separator(arguments)
    for argument in wrapper:
        option = argument.split("=", 1)[0]
        if option.startswith("--") and option not in LAUNCHER_LONG_OPTIONS:
            matches = [
                candidate
                for candidate in LAUNCHER_LONG_OPTIONS
                if candidate.startswith(option)
            ]
            if matches:
                expected = " or ".join(matches)
                raise LauncherError(
                    f"abbreviated launcher option {option!r} is not supported; "
                    f"use {expected}"
                )
    positional_client = (
        wrapper.pop(0) if wrapper[:1] and wrapper[0] in CLIENTS else None
    )
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--client", choices=CLIENTS)
    parser.add_argument(
        "--agent", "--role", dest="agent", choices=PUBLIC_AGENTS
    )
    options, _ = parser.parse_known_args(wrapper)
    if options.client and positional_client and options.client != positional_client:
        parser.error("positional client and --client disagree")
    return options.client or positional_client, options.agent


def defaults_for_arguments(
    arguments: Sequence[str],
    validation_cache: dict[str, LaunchChecks] | None = None,
) -> Preferences | None:
    explicit_client, explicit_agent = _explicit_selection(arguments)
    if explicit_client is not None and explicit_agent is not None:
        return None
    current = load_preferences()
    if current is not None:
        return current
    if sys.stdin.isatty() and sys.stdout.isatty():
        print_only = _contains_option(_split_separator(arguments)[0], "--print-command")
        return choose_preferences(
            fixed_client=explicit_client,
            fixed_agent=explicit_agent,
            validate=not print_only,
            persist=not print_only,
            validation_cache=validation_cache,
        )
    raise LauncherError(
        "no saved default in a non-interactive terminal; use --client and --agent"
    )


def _doctor_arguments(arguments: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="grillmester doctor",
        allow_abbrev=False,
        description="Check the Grillmester payload and terminal clients without launching.",
    )
    parser.add_argument("--client", choices=CLIENTS)
    return parser.parse_args(arguments)


def _run_local_mode(arguments: Sequence[str]) -> int:
    local_mode = _load_local_mode_module()
    normalize = getattr(local_mode, "normalize_cli_arguments", None)
    if not callable(normalize):
        raise LauncherError("bundled local launcher exposes no argument normalizer")
    local_arguments = normalize(arguments)
    if not isinstance(local_arguments, list) or not all(
        isinstance(argument, str) for argument in local_arguments
    ):
        raise LauncherError("bundled local launcher returned invalid arguments")

    command = local_arguments[0] if local_arguments else ""
    distribution: Distribution | None = None
    binary_resolver = None
    if command in {"doctor", "launch", "run"}:
        distribution = load_distribution()

        def resolve_local_binaries(
            client: str, checked: bool, project_dir: Path
        ) -> tuple[CheckedBinary, CheckedBinary]:
            assert distribution is not None
            if not checked:
                return (
                    CheckedBinary("cplt", _resolve_binary("cplt")),
                    CheckedBinary(client, _resolve_binary(client)),
                )
            cplt_path = _resolve_binary("cplt")
            client_path = _resolve_binary(client)
            prepare_probe = getattr(
                local_mode, "prepare_client_version_probe", None
            )
            if not callable(prepare_probe):
                raise LauncherError(
                    "bundled local launcher exposes no safe version-probe builder"
                )
            cleanup_probe = getattr(
                local_mode, "cleanup_client_version_probe", None
            )
            if not callable(cleanup_probe):
                raise LauncherError(
                    "bundled local launcher exposes no safe version-probe cleanup"
                )
            probe = prepare_probe(
                client_name=client,
                cplt=cplt_path,
                client=client_path,
                distribution_root=distribution.root,
                project_dir=project_dir,
                environment=os.environ,
            )
            try:
                probe_environment = getattr(probe, "environment", None)
                probe_cplt_arguments = getattr(probe, "cplt_arguments", None)
                if not isinstance(probe_environment, Mapping) or not isinstance(
                    probe_cplt_arguments, tuple
                ) or not all(
                    isinstance(argument, str) for argument in probe_cplt_arguments
                ):
                    raise LauncherError(
                        "bundled local launcher returned an invalid version-probe context"
                    )
                cplt = check_cplt(
                    binary=cplt_path,
                    environment=probe_environment,
                )
                runtime = check_client_runtime(
                    client,
                    cplt=cplt,
                    distribution=distribution,
                    binary=client_path,
                    probe_environment=probe_environment,
                    probe_cplt_arguments=probe_cplt_arguments,
                )
                return cplt, runtime
            finally:
                cleanup_probe(probe)

        binary_resolver = resolve_local_binaries

    local_main = getattr(local_mode, "main", None)
    if not callable(local_main):
        raise LauncherError("bundled local launcher exposes no callable main")
    result = local_main(
        local_arguments,
        distribution_root=distribution.root if distribution is not None else None,
        binary_resolver=binary_resolver,
    )
    if not isinstance(result, int):
        raise LauncherError("bundled local launcher returned no integer status")
    return result


def main(arguments: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if arguments is None else arguments)
    validation_cache: dict[str, LaunchChecks] = {}
    try:
        if arguments[:1] == ["local"]:
            return _run_local_mode(arguments[1:])
        if arguments[:1] == ["doctor"]:
            options = _doctor_arguments(arguments[1:])
            return doctor(options.client)
        if arguments in (["--help"], ["-h"], ["help"]):
            parse_invocation(["--help"])
            return 0
        if arguments[:1] in (["update"], ["upgrade"]):
            if len(arguments) != 1:
                raise LauncherError(
                    f"grillmester {arguments[0]} takes no arguments"
                )
            update_installation()
            return 0
        if arguments == ["--version"] or arguments == ["version"]:
            distribution = load_distribution()
            print(f"grillmester {distribution.version}")
            return 0
        if arguments[:1] == ["choose"]:
            if len(arguments) != 1:
                raise LauncherError("grillmester choose takes no arguments")
            try:
                current = load_preferences()
            except InvalidPreferencesError as exc:
                print(f"Advarsel: {exc}", file=sys.stderr)
                current = None
            choose_preferences(current)
            return 0
        wrapper, _ = _split_separator(arguments)
        if any(argument in ("-h", "--help") for argument in wrapper):
            parse_invocation(arguments)
            return 0
        if not arguments:
            defaults = interactive_defaults(validation_cache)
            if defaults is None:
                return 0
            invocation = parse_invocation([], defaults=defaults)
        else:
            invocation = parse_invocation(
                arguments,
                defaults=defaults_for_arguments(arguments, validation_cache),
            )
        distribution = load_distribution()
        if invocation.print_command:
            cplt = _resolve_binary("cplt")
            _resolve_binary(invocation.client)
        else:
            checks = validation_cache.get(invocation.client)
            if checks is None:
                checks = check_client(
                    invocation.client,
                    distribution=distribution,
                )
            cplt = checks.cplt.path
        command, environment = build_launch_command(
            invocation, distribution, cplt=cplt
        )
        if invocation.print_command:
            print(shlex.join(command))
            return 0
        if invocation.client == "opencode":
            ensure_opencode_runtime_support(distribution, environment)
        print(
            f"Launching Grillmester ({invocation.agent}) in {invocation.client} "
            "through cplt...",
            file=sys.stderr,
        )
        os.execvpe(command[0], command, environment)
    except (LauncherError, OSError) as exc:
        print(f"grillmester: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
