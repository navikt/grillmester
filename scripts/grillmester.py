#!/usr/bin/env python3
"""Launch a Grillmester client, inside cplt's sandbox when cplt is installed."""

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


SUPPORTED_CPLT_RELEASE = "2026.11.02-225238-10a2882"
MINIMUM_OPENCODE_VERSION_TEXT = "2.2.5"
MINIMUM_OPENCODE_VERSION = tuple(
    int(part) for part in MINIMUM_OPENCODE_VERSION_TEXT.split(".")
)
SUPPORTED_OPENCODE_MAJOR = MINIMUM_OPENCODE_VERSION[0]
MINIMUM_COPILOT_VERSION = (1, 0, 100)
SUPPORTED_COPILOT_MAJOR = MINIMUM_COPILOT_VERSION[0]
CLIENTS = ("copilot", "opencode")
PUBLIC_AGENTS = ("grillmester", "designer", "doctor-who")
CPLT_SUBCOMMANDS = frozenset(
    {
        "check",
        "config",
        "doctor",
        "exec",
        "help",
        "init",
        "link",
        "mcp",
        "settings",
        "trust",
        "update",
        "update-lists",
        "worktree",
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
    rf"^(?:OpenCode(?: version)? )?v?{SEMVER_PATTERN}$",
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
AGENT_LABELS = {
    "grillmester": "Grillmester – utvikling, fra små endringer til komplekse oppgaver",
    "designer": "Designer – design, prototyper og brukerflyt",
    "doctor-who": "Doctor Who – discovery, produkt og arkitektur",
}
CLIENT_LABELS = {
    "copilot": "GitHub Copilot CLI",
    "opencode": "OpenCode",
}
OPENCODE_LAUNCH_ENVIRONMENT = (
    "OPENCODE_CONFIG_DIR",
    "OPENCODE_CONFIG_CONTENT",
    "OPENCODE_DISABLE_FREE_MODELS",
)
OPENCODE_USER_CONFIG_NAMES = ("opencode.json", "opencode.jsonc")
# These reject --standalone, and they start no agent session.
OPENCODE_SERVER_COMMANDS = frozenset(
    {"acp", "pair", "serve", "service", "uninstall", "update", "upgrade"}
)
LAUNCHER_LONG_OPTIONS = (
    "--agent",
    "--client",
    "--no-cplt",
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
    no_cplt: bool = False


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
    cplt: CheckedBinary | None
    client: CheckedBinary


def distribution_root() -> Path:
    """Resolve through a symlink to the immutable bundle root."""

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

    # Extracting a tarball over an older bundle does not remove retired files.
    # Refuse the mixed payload before either client discovers the obsolete role;
    # cleanup belongs to the installation owner, not this launcher.
    for role, payload, filename in (
        ("Barista", plugin, "barista.agent.md"),
        ("Barista", target, "barista.md"),
        ("Barista", focused_opencode, "barista.md"),
        ("Barista", focused_copilot, "barista.agent.md"),
        ("Kokk", plugin, "kokk.agent.md"),
        ("Kokk", target, "kokk.md"),
    ):
        retired = payload / "agents" / filename
        if retired.exists() or retired.is_symlink():
            raise LauncherError(
                f"mixed installation contains retired {role} file: {retired}; "
                "extract the release bundle into a new empty directory and point "
                "the launcher at it; keep your saved configuration"
            )

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
    if not isinstance(counts, dict) or counts.get("agents") != 6 or counts.get(
        "skills"
    ) != 37:
        raise LauncherError("OpenCode target manifest does not contain 6 agents and 37 skills")
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
            or manifest.get("agents") != ["grill-inspektor", "grillmester"]
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
    # Retire the saved role without losing the user's selected client. Reading
    # preferences remains side-effect free; the next save writes the new ID.
    if agent == "barista":
        agent = "grillmester"
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


def _split_separator(arguments: Sequence[str]) -> tuple[list[str], list[str]]:
    try:
        separator = arguments.index("--")
    except ValueError:
        return list(arguments), []
    return list(arguments[:separator]), list(arguments[separator + 1 :])


def _public_agent(value: str) -> str:
    if value == "barista":
        raise argparse.ArgumentTypeError(
            "Barista has been retired; use --agent grillmester "
            "with your preferred model"
        )
    return value


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
        description=(
            "Launch Grillmester in Copilot CLI or OpenCode, inside cplt's sandbox "
            "when cplt is installed."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Commands:\n"
            "  choose    change and save the default without launching\n"
            "  doctor    verify the distribution and installed clients\n"
            "  local     use one configured loopback model (focused by default)\n"
            "  help      show this help\n"
            "  version   show the installed Grillmester version\n\n"
            "Examples:\n"
            "  grillmester\n"
            "  grillmester doctor --client opencode\n"
            "  grillmester --client opencode --agent grillmester\n"
            "  grillmester local setup\n"
            "  grillmester local\n"
            "  grillmester local --full\n"
            "  grillmester --client copilot --agent designer --print-command\n\n"
            "Arguments unknown to Grillmester are forwarded to cplt. Arguments "
            "after -- go to the selected client. Without cplt the client starts "
            "directly, with no sandbox around it."
        ),
    )
    client_name = wrapper.pop(0) if wrapper[:1] and wrapper[0] in CLIENTS else None
    parser.add_argument(
        "--client", choices=CLIENTS, help="terminal client to start"
    )
    parser.add_argument(
        "--agent",
        "--role",
        dest="agent",
        type=_public_agent,
        choices=PUBLIC_AGENTS,
        help="public Grillmester agent (--role remains a compatible alias)",
    )
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=cwd or Path.cwd(),
        help="consumer repository to work in (default: current directory)",
    )
    parser.add_argument(
        "--print-command",
        action="store_true",
        help="print the exact launch command without starting a client",
    )
    parser.add_argument(
        "--no-cplt",
        action="store_true",
        help="start the client directly, even when cplt is installed",
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
        no_cplt=options.no_cplt,
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
    if client == "opencode" and _contains_option(client_args, "--standalone"):
        raise LauncherError(
            "OpenCode --standalone is owned by Grillmester, which sets it when "
            "the client starts without cplt"
        )
    if client == "copilot" and _contains_option(client_args, "--plugin-dir"):
        raise LauncherError(
            "Copilot --plugin-dir is owned by Grillmester's reviewed distribution"
        )


def _opencode_config_content(agent: str, current: str | None) -> str:
    """Select the agent in the only place OpenCode 2's TUI reads it from."""

    try:
        content = json.loads(current) if current else {}
    except ValueError as exc:
        raise LauncherError(f"OPENCODE_CONFIG_CONTENT is not valid JSON: {exc}") from exc
    if not isinstance(content, dict):
        raise LauncherError("OPENCODE_CONFIG_CONTENT must be a JSON object")
    content["default_agent"] = agent
    return json.dumps(content, sort_keys=True, separators=(",", ":"))


def _user_opencode_config(environment: Mapping[str, str]) -> Path | None:
    """Find the file OpenCode 2 stops reading once OPENCODE_CONFIG_DIR is set."""

    directory = config_home(environment) / "opencode"
    for name in OPENCODE_USER_CONFIG_NAMES:
        if (directory / name).is_file():
            return directory / name
    return None


def _client_launch(
    invocation: Invocation, distribution: Distribution
) -> tuple[list[str], dict[str, str]]:
    """Return the client arguments and environment both launch modes share."""

    environment = dict(os.environ)
    if invocation.client == "copilot":
        return [
            "--plugin-dir",
            str(distribution.plugin),
            "--agent",
            f"grillmester:{invocation.agent}",
            *invocation.client_args,
        ], environment
    environment["OPENCODE_CONFIG_DIR"] = str(distribution.opencode_target)
    environment["OPENCODE_CONFIG_CONTENT"] = _opencode_config_content(
        invocation.agent, environment.get("OPENCODE_CONFIG_CONTENT")
    )
    # With no provider, OpenCode would otherwise send the code to a free cloud model.
    environment.setdefault("OPENCODE_DISABLE_FREE_MODELS", "true")
    forwarded = list(invocation.client_args)
    if forwarded[:1] == ["run"]:
        return ["run", "--agent", invocation.agent, *forwarded[1:]], environment
    return forwarded, environment


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
    client_arguments, environment = _client_launch(invocation, distribution)
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
    if invocation.client == "opencode":
        for name in OPENCODE_LAUNCH_ENVIRONMENT:
            command.extend(("--pass-env", name))
    command.extend(invocation.cplt_args)
    command.append("--")
    command.extend(client_arguments)
    return command, environment


def build_direct_command(
    invocation: Invocation,
    distribution: Distribution,
    *,
    client: str,
) -> tuple[list[str], dict[str, str]]:
    """Start the client in the project directory, without a sandbox."""

    client_arguments, environment = _client_launch(invocation, distribution)
    # OpenCode's `run` trusts PWD over the real working directory.
    environment["PWD"] = str(invocation.project_dir)
    if invocation.client == "copilot":
        # cplt adds this flag itself.
        client_arguments.insert(0, "--no-auto-update")
    else:
        if client_arguments[:1] and client_arguments[0] in OPENCODE_SERVER_COMMANDS:
            raise LauncherError(
                f"'opencode {client_arguments[0]}' starts no agent session; "
                "run it yourself without Grillmester"
            )
        # OpenCode 2 otherwise starts a shared background service and stores
        # its password in OPENCODE_CONFIG_DIR, which is our distributed target.
        # cplt runs its own service for each session and rejects this flag.
        client_arguments.insert(0, "--standalone")
        user_config = _user_opencode_config(environment)
        if user_config is not None:
            environment.setdefault("OPENCODE_CONFIG", str(user_config))
    return [client, *client_arguments], environment


def _printable_command(
    invocation: Invocation,
    command: Sequence[str],
    environment: Mapping[str, str],
    *,
    direct: bool,
) -> str:
    assignments: list[str] = []
    if invocation.client == "opencode":
        for name in (*OPENCODE_LAUNCH_ENVIRONMENT, "OPENCODE_CONFIG"):
            if name in environment:
                assignments.append(f"{name}={_printable_value(name, environment)}")
    printed = shlex.join(["env", *assignments, *command] if assignments else command)
    if direct:
        return f"cd {shlex.quote(str(invocation.project_dir))} && {printed}"
    return printed


def _printable_value(name: str, environment: Mapping[str, str]) -> str:
    """Keep provider keys in inline configuration out of terminal scrollback."""

    value = environment[name]
    if name == "OPENCODE_CONFIG_CONTENT" and set(json.loads(value)) != {"default_agent"}:
        return "<your OPENCODE_CONFIG_CONTENT with default_agent set>"
    return value


CLIENT_INSTALL_HINTS = {
    "copilot": "brew install --cask copilot-cli",
    "cplt": "brew install navikt/tap/cplt",
    "opencode": "brew install opencode",
}
CPLT_UPDATE_HINT = "brew upgrade navikt/tap/cplt"


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
    """Inspect cplt before it becomes the trust boundary."""

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
    cwd: Path | None = None,
    timeout: float = 30,
    max_output_bytes: int = 64 * 1024,
) -> tuple[int, str, str]:
    """Run one client probe with bounded output and whole-group timeout cleanup."""

    try:
        process = subprocess.Popen(
            list(command),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=dict(environment),
            cwd=cwd,
            start_new_session=True,
        )
    except OSError as exc:
        raise LauncherError(f"could not start client probe: {exc}") from exc
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
                    f"client version probe timed out after {timeout:g} seconds"
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
                        "client version probe exceeded the "
                        f"{max_output_bytes}-byte output limit"
                    )
        try:
            returncode = process.wait(timeout=max(0.0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            _terminate_process_group(process)
            process.wait()
            raise LauncherError(
                f"client version probe timed out after {timeout:g} seconds"
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
            "client version probe did not return UTF-8 output"
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


def _direct_client_version(client: str, *, binary: str) -> str:
    with tempfile.TemporaryDirectory(prefix="grillmester-client-probe-") as directory:
        returncode, stdout, stderr = _bounded_command_output(
            [binary, "--version"],
            environment=os.environ,
            cwd=Path(directory),
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
            f"{CLIENT_LABELS[client]} version probe failed with "
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
            f"{CLIENT_LABELS[client]} version probe returned "
            f"unexpected stdout; expected one strict version line"
        )
    raise LauncherError(
        f"{CLIENT_LABELS[client]} version probe returned an "
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
            f"{SUPPORTED_CPLT_RELEASE} or a newer release; found {cplt_version!r}; "
            f"update it with: {CPLT_UPDATE_HINT} (a standard launch can also "
            "start without it with --no-cplt)"
        )
    return CheckedBinary("cplt", cplt, cplt_version)


def resolve_cplt(*, disabled: bool = False) -> CheckedBinary | None:
    """Return the sandbox to launch through, or None to start the client directly.

    An installed cplt that fails its check stays an error, so nobody loses the
    sandbox they chose without saying so.
    """

    if disabled:
        return None
    cplt = _find_cplt()
    return None if cplt is None else check_cplt(binary=cplt)


def _find_cplt() -> str | None:
    """Tell an absent cplt from a broken one, which `which` also skips."""

    try:
        return _resolve_binary("cplt")
    except MissingBinaryError:
        for directory in os.environ.get("PATH", "").split(os.pathsep):
            candidate = Path(directory or os.curdir) / "cplt"
            if os.path.lexists(candidate) and not candidate.is_dir():
                raise LauncherError(
                    f"{candidate} is not a working cplt; fix it, or start without "
                    "its sandbox with --no-cplt"
                ) from None
        return None


def check_client_runtime(
    client: str,
    *,
    cplt: CheckedBinary | None,
    distribution: Distribution,
    binary: str | None = None,
    probe_environment: Mapping[str, str] | None = None,
    probe_cplt_arguments: Sequence[str] = (),
) -> CheckedBinary:
    binary = _resolve_binary(client) if binary is None else binary
    if cplt is None:
        version = _direct_client_version(client, binary=binary)
    else:
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
                f"OpenCode must be in the supported {SUPPORTED_OPENCODE_MAJOR}.x "
                "range, starting at "
                f"{MINIMUM_OPENCODE_VERSION_TEXT}; found {version!r}; "
                f"install it with: {CLIENT_INSTALL_HINTS['opencode']}"
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
                f"{minimum}; found {version!r}; update it with: "
                "brew upgrade --cask copilot-cli"
            )
    return CheckedBinary(client, binary, version)


def check_client(
    client: str,
    *,
    distribution: Distribution | None = None,
    no_cplt: bool = False,
) -> LaunchChecks:
    distribution = load_distribution() if distribution is None else distribution
    cplt = resolve_cplt(disabled=no_cplt)
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
            f"with '{CLIENT_INSTALL_HINTS['opencode']}', or GitHub Copilot CLI "
            f"with '{CLIENT_INSTALL_HINTS['copilot']}'"
        )
    return tuple(available)


def doctor(
    client: str | None, *, root: Path | None = None, no_cplt: bool = False
) -> int:
    distribution = load_distribution(root)
    print(f"ok  distribution {distribution.root} (v{distribution.version})")
    print(f"ok  copilot plugin {distribution.plugin}")
    print(f"ok  OpenCode target {distribution.opencode_target}")
    print(f"ok  focused Copilot CLI target {distribution.focused_copilot_target}")
    print(f"ok  focused OpenCode target {distribution.focused_opencode_target}")
    try:
        cplt_check = resolve_cplt(disabled=no_cplt)
    except LauncherError as exc:
        print(f"error  cplt: {exc}", file=sys.stderr)
        return 1
    if cplt_check is not None:
        print(f"ok  {cplt_check.label} {cplt_check.detail}")
    elif no_cplt:
        print("skip  cplt (--no-cplt)")
    else:
        print(
            "skip  cplt not installed (optional; clients start without its "
            f"sandbox; install it with: {CLIENT_INSTALL_HINTS['cplt']})"
        )

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
    no_cplt: bool = False,
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
        checks = check_client(client, no_cplt=no_cplt)
        if validation_cache is not None:
            validation_cache[client] = checks
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
    sandbox = "gjennom cplt" if _find_cplt() else "uten sandbox"
    prompt = (
        f"Start {CLIENT_LABELS[current.client]} med "
        f"{AGENT_LABELS[current.agent].split(' – ', 1)[0]} {sandbox}? "
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
        "--agent", "--role", dest="agent", type=_public_agent, choices=PUBLIC_AGENTS
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
        wrapper = _split_separator(arguments)[0]
        print_only = _contains_option(wrapper, "--print-command")
        return choose_preferences(
            fixed_client=explicit_client,
            fixed_agent=explicit_agent,
            validate=not print_only,
            persist=not print_only,
            validation_cache=validation_cache,
            no_cplt=_contains_option(wrapper, "--no-cplt"),
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
    parser.add_argument(
        "--no-cplt",
        action="store_true",
        help="check the clients as they start without cplt",
    )
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
            return doctor(options.client, no_cplt=options.no_cplt)
        if arguments in (["--help"], ["-h"], ["help"]):
            parse_invocation(["--help"])
            return 0
        if arguments == ["--version"] or arguments == ["version"]:
            distribution = load_distribution()
            print(f"grillmester {distribution.version}")
            return 0
        if arguments[:1] in (["update"], ["upgrade"]):
            raise LauncherError(
                f"grillmester {arguments[0]} is no longer a command; Grillmester "
                "is updated by extracting a newer release bundle into a new empty "
                "directory and pointing the launcher at it; keep your saved configuration"
            )
        if arguments[:1] == ["choose"]:
            if arguments[1:] not in ([], ["--no-cplt"]):
                raise LauncherError("grillmester choose takes only --no-cplt")
            try:
                current = load_preferences()
            except InvalidPreferencesError as exc:
                print(f"Advarsel: {exc}", file=sys.stderr)
                current = None
            choose_preferences(current, no_cplt=len(arguments) == 2)
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
            client = _resolve_binary(invocation.client)
            cplt = None if invocation.no_cplt else _find_cplt()
        else:
            checks = validation_cache.get(invocation.client)
            if checks is None:
                checks = check_client(
                    invocation.client,
                    distribution=distribution,
                    no_cplt=invocation.no_cplt,
                )
            client = checks.client.path
            cplt = None if checks.cplt is None else checks.cplt.path
        if cplt is None:
            if invocation.cplt_args:
                raise LauncherError(
                    "these arguments need cplt, which is not in use: "
                    f"{shlex.join(invocation.cplt_args)}; arguments for the "
                    "client go after --"
                )
            command, environment = build_direct_command(
                invocation, distribution, client=client
            )
        else:
            command, environment = build_launch_command(
                invocation, distribution, cplt=cplt
            )
        if invocation.print_command:
            print(
                _printable_command(
                    invocation, command, environment, direct=cplt is None
                )
            )
            return 0
        if cplt is None:
            print(
                f"Launching Grillmester ({invocation.agent}) in "
                f"{invocation.client} without the cplt sandbox...",
                file=sys.stderr,
            )
            os.chdir(invocation.project_dir)
        else:
            print(
                f"Launching Grillmester ({invocation.agent}) in "
                f"{invocation.client} through cplt...",
                file=sys.stderr,
            )
            if invocation.client == "opencode":
                user_config = environment.get(
                    "OPENCODE_CONFIG"
                ) or _user_opencode_config(environment)
                if user_config is not None:
                    print(
                        f"cplt does not load {user_config} for this target; "
                        "use /connect, OPENCODE_CONFIG_CONTENT or --no-cplt "
                        "for your own providers",
                        file=sys.stderr,
                    )
        os.execvpe(command[0], command, environment)
    except (LauncherError, OSError) as exc:
        print(f"grillmester: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
