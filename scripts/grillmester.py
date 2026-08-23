#!/usr/bin/env python3
"""Launch a reviewed Grillmester client through cplt."""

from __future__ import annotations

import argparse
import errno
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence


SUPPORTED_CPLT_RELEASE = "2026.08.17-062831-1008a92"
SUPPORTED_OPENCODE_VERSION = "1.18.20"
MINIMUM_COPILOT_VERSION = (1, 0, 79)
CLIENTS = ("copilot", "opencode")
PUBLIC_AGENTS = ("grillmester", "barista", "designer", "doctor-who")
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
VERSION_PATTERN = re.compile(
    r"(?<![0-9.])(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.-]+)?"
    r"(?![0-9]|\.[0-9])"
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
    version: str


@dataclass(frozen=True)
class Preferences:
    client: str
    agent: str


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
    if not plugin.is_dir() or plugin.is_symlink():
        raise LauncherError(f"distribution has no regular plugin directory: {plugin}")
    if not target.is_dir() or target.is_symlink():
        raise LauncherError(f"distribution has no regular OpenCode target: {target}")

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
    return Distribution(root, plugin, target, version)


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
        description="Launch Grillmester in Copilot CLI or OpenCode through cplt.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Commands:\n"
            "  choose    change and save the default without launching\n"
            "  doctor    verify the distribution and installed clients\n"
            "  update    update the Homebrew installation\n"
            "  help      show this help\n"
            "  version   show the installed Grillmester version\n\n"
            "Examples:\n"
            "  grillmester\n"
            "  grillmester doctor --client opencode\n"
            "  grillmester --client opencode --agent barista\n"
            "  grillmester --client opencode --agent grillmester "
            "--allow-localhost 1234 -- --model lmstudio/example\n"
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
        client_prefix = ["--agent", invocation.agent]
    else:
        client_prefix = [
            "--plugin-dir",
            str(distribution.plugin),
            "--agent",
            f"grillmester:{invocation.agent}",
        ]
    command.extend(invocation.cplt_args)
    command.append("--")
    command.extend(client_prefix)
    command.extend(invocation.client_args)
    return command, environment


def _resolve_binary(name: str) -> str:
    resolved = shutil.which(name)
    if resolved is None:
        install = (
            "brew install --cask copilot-cli"
            if name == "copilot"
            else f"brew install {name}"
        )
        if name == "cplt":
            install = "brew install navikt/tap/cplt"
        raise MissingBinaryError(
            f"{name} was not found on PATH; install it with: {install}"
        )
    return str(Path(resolved).resolve(strict=True))


def _version_output(binary: str) -> str:
    try:
        result = subprocess.run(
            [binary, "--version"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LauncherError(f"could not inspect {binary}: {exc}") from exc
    output = result.stdout.strip()
    if result.returncode != 0 or not output:
        raise LauncherError(f"{binary} --version failed with exit {result.returncode}")
    return output.splitlines()[0].strip()


def _copilot_semver(output: str) -> tuple[int, int, int]:
    match = VERSION_PATTERN.search(output)
    if match is None:
        raise LauncherError(f"could not parse Copilot CLI version from {output!r}")
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def check_cplt() -> tuple[str, str]:
    cplt = _resolve_binary("cplt")
    cplt_version = _version_output(cplt)
    expected_cplt = f"cplt {SUPPORTED_CPLT_RELEASE}"
    if cplt_version != expected_cplt:
        raise LauncherError(
            f"cplt must be exactly {expected_cplt!r}; found {cplt_version!r}"
        )
    return "cplt", f"{cplt} ({cplt_version})"


def check_client_runtime(client: str) -> tuple[str, str]:
    binary = _resolve_binary(client)
    version = _version_output(binary)
    if client == "opencode":
        if version != SUPPORTED_OPENCODE_VERSION:
            raise LauncherError(
                "OpenCode must be exactly "
                f"{SUPPORTED_OPENCODE_VERSION!r}; found {version!r}"
            )
    elif _copilot_semver(version) < MINIMUM_COPILOT_VERSION:
        minimum = ".".join(str(part) for part in MINIMUM_COPILOT_VERSION)
        raise LauncherError(
            f"Copilot CLI must be at least {minimum}; found {version!r}"
        )
    return client, f"{binary} ({version})"


def check_client(client: str) -> list[tuple[str, str]]:
    return [check_cplt(), check_client_runtime(client)]


def update_installation() -> None:
    """Refresh Homebrew metadata and replace this installation explicitly."""

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
    try:
        cplt_check = check_cplt()
    except LauncherError as exc:
        print(f"error  cplt: {exc}", file=sys.stderr)
        return 1
    print(f"ok  {cplt_check[0]} {cplt_check[1]}")

    selected = CLIENTS if client is None else (client,)
    failed = False
    available = 0
    for candidate in selected:
        try:
            label, detail = check_client_runtime(candidate)
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
        print(f"ok  {label} {detail}")
    if client is None and available == 0:
        print("error  no supported terminal client was found on PATH", file=sys.stderr)
        failed = True
    return 1 if failed else 0


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
        answer = input(f"Velg [Enter = {labels[default]}]: ").strip()
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
) -> Preferences:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise LauncherError(
            "interactive selection requires a terminal; use --client and --agent"
        )
    default_client = current.client if current is not None else "copilot"
    default_agent = current.agent if current is not None else "grillmester"
    print("\nHva vil du starte?\n")
    if fixed_client is None:
        client = _read_choice("Klient", CLIENTS, CLIENT_LABELS, default_client)
    else:
        client = fixed_client
        print(f"Klient\n  {CLIENT_LABELS[client]} (fra kommandoen)")
    print()
    if fixed_agent is None:
        agent = _read_choice("Agent", PUBLIC_AGENTS, AGENT_LABELS, default_agent)
    else:
        agent = fixed_agent
        print(f"Agent\n  {AGENT_LABELS[agent]} (fra kommandoen)")
    preferences = Preferences(client, agent)
    path = save_preferences(preferences)
    print(
        f"\nLagret default: {CLIENT_LABELS[client]} med "
        f"{AGENT_LABELS[agent].split(' – ', 1)[0]}"
    )
    print(f"Preferanser: {path}\n")
    return preferences


def interactive_defaults() -> Preferences | None:
    current = load_preferences()
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        if current is None:
            raise LauncherError(
                "no saved default in a non-interactive terminal; use --client and --agent"
            )
        return current
    if current is None:
        return choose_preferences()
    prompt = (
        f"Start {CLIENT_LABELS[current.client]} med "
        f"{AGENT_LABELS[current.agent].split(' – ', 1)[0]} gjennom cplt? "
        "[Enter = start, c = endre, q = avslutt]: "
    )
    while True:
        answer = input(prompt).strip().lower()
        if answer in ("", "s", "start"):
            return current
        if answer in ("c", "change", "endre"):
            return choose_preferences(current)
        if answer in ("q", "quit", "avslutt"):
            return None
        print("Ugyldig valg. Trykk Enter, c eller q.")


def _explicit_selection(arguments: Sequence[str]) -> tuple[str | None, str | None]:
    wrapper, _ = _split_separator(arguments)
    positional_client = (
        wrapper.pop(0) if wrapper[:1] and wrapper[0] in CLIENTS else None
    )
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--client", choices=CLIENTS)
    parser.add_argument(
        "--agent", "--role", dest="agent", choices=PUBLIC_AGENTS
    )
    options, _ = parser.parse_known_args(wrapper)
    if options.client and positional_client and options.client != positional_client:
        parser.error("positional client and --client disagree")
    return options.client or positional_client, options.agent


def defaults_for_arguments(arguments: Sequence[str]) -> Preferences | None:
    explicit_client, explicit_agent = _explicit_selection(arguments)
    if explicit_client is not None and explicit_agent is not None:
        return None
    current = load_preferences()
    if current is not None:
        return current
    if sys.stdin.isatty() and sys.stdout.isatty():
        return choose_preferences(
            fixed_client=explicit_client,
            fixed_agent=explicit_agent,
        )
    raise LauncherError(
        "no saved default in a non-interactive terminal; use --client and --agent"
    )


def _doctor_arguments(arguments: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="grillmester doctor",
        description="Check the Grillmester payload and terminal clients without launching.",
    )
    parser.add_argument("--client", choices=CLIENTS)
    return parser.parse_args(arguments)


def _has_explicit_selection(arguments: Sequence[str], option: str) -> bool:
    wrapper, _ = _split_separator(arguments)
    if option == "--client" and wrapper[:1] and wrapper[0] in CLIENTS:
        return True
    return _contains_option(wrapper, option)


def main(arguments: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if arguments is None else arguments)
    try:
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
        elif not arguments:
            defaults = interactive_defaults()
            if defaults is None:
                return 0
            invocation = parse_invocation([], defaults=defaults)
        else:
            invocation = parse_invocation(
                arguments, defaults=defaults_for_arguments(arguments)
            )
        distribution = load_distribution()
        checks = check_client(invocation.client)
        cplt = next(detail.split(" (", 1)[0] for label, detail in checks if label == "cplt")
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
