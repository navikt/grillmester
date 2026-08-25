#!/usr/bin/env python3
"""Configure and launch Grillmester against one explicit local model.

This module owns neither the model server, terminal clients nor their sandbox.
It stores a small connection description, binds inference to an explicit
OpenAI-compatible loopback endpoint, and delegates runtime enforcement to cplt.
External tools remain available through the client's normal approval model and
cplt's proxy, GitHub guard and Git guard.
"""

from __future__ import annotations

import argparse
import errno
import fcntl
import hashlib
import http.client
import ipaddress
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable, Mapping, Sequence
from urllib.parse import urlsplit


CONFIG_SCHEMA_VERSION = 2
CONFIG_FILE = "local.json"
CLIENTS = frozenset({"copilot", "opencode"})
CONTEXTS = frozenset({"focused", "full"})
PUBLIC_AGENTS = frozenset({"grillmester", "barista", "designer", "doctor-who"})
FOCUSED_AGENT = "barista"
OPENCODE_SAFE_META_ARGUMENTS = frozenset(
    {("-h",), ("--help",), ("-v",), ("--version",)}
)
COPILOT_SAFE_META_ARGUMENTS = frozenset(
    {("help",), ("version",)}
)
COPILOT_SAFE_BOOLEAN_OPTIONS = frozenset(
    {
        "--banner",
        "--disallow-temp-dir",
        "--enable-reasoning-summaries",
        "--help",
        "--no-ask-user",
        "--no-bash-env",
        "--no-color",
        "--no-custom-instructions",
        "--no-mouse",
        "--plain-diff",
        "--plan",
        "--screen-reader",
        "--version",
    }
)
COPILOT_SAFE_VALUE_OPTIONS = frozenset(
    {
        "--attachment",
        "--context",
        "--disable-mcp-server",
        "--effort",
        "--interactive",
        "--log-level",
        "--max-ai-credits",
        "--name",
        "--output-format",
        "--prompt",
        "--reasoning-effort",
        "--stream",
    }
)
COPILOT_SAFE_OPTIONAL_VALUE_OPTIONS = frozenset(
    {
        "--available-tools",
        "--deny-tool",
        "--deny-url",
        "--excluded-tools",
        "--mouse",
    }
)
OPENCODE_SAFE_BOOLEAN_OPTIONS = frozenset(
    {
        "--help",
        "--mini",
        "--no-replay",
        "--print-logs",
        "--pure",
        "--version",
    }
)
OPENCODE_SAFE_VALUE_OPTIONS = frozenset(
    {
        "--log-level",
        "--replay-limit",
    }
)
COPILOT_SECRET_ENV = "COPILOT_PROVIDER_API_KEY"
COPILOT_GITHUB_SECRET_ENVIRONMENTS = (
    "GITHUB_TOKEN",
    "COPILOT_GITHUB_TOKEN",
)
GITHUB_SECRET_ENV = "GH_TOKEN"
MAX_CONFIG_BYTES = 64 * 1024
MAX_SECRET_BYTES = 16 * 1024
MAX_GITHUB_TOKEN_BYTES = 4 * 1024
MAX_PROBE_BYTES = 256 * 1024
DEFAULT_PROBE_TIMEOUT = 5.0
DEFAULT_BASE_URL = "http://127.0.0.1:8080/v1"
RECOMMENDED_LOCAL_SERVER_CONTEXT_WINDOW = 65_536
DEFAULT_MAX_OUTPUT_TOKENS = 8_192
# Keep one output-sized margin between the server capacity and the context
# advertised to the harness. OpenCode and Copilot can add tool and protocol
# overhead outside the model-visible conversation budget.
DEFAULT_CONTEXT_WINDOW = (
    RECOMMENDED_LOCAL_SERVER_CONTEXT_WINDOW - DEFAULT_MAX_OUTPUT_TOKENS
)
DEFAULT_COPILOT_REASONING_EFFORT = "medium"
# The focused prompt and OpenCode's native preflight compaction both need real
# headroom. Smaller windows can fail before a useful conversation exists to
# compact, so they are outside the supported local coding profile.
MINIMUM_CONTEXT_WINDOW = 32_768
RETAINED_INACTIVE_SESSIONS = 2
SESSION_OWNER_FILE = "owner.pid"

LOCAL_ROUTABLE_VALUE_OPTIONS = (
    "--project-dir",
    "--client",
    "--agent",
)
LOCAL_ROUTABLE_FLAG_OPTIONS = (
    "--full",
    "--print-command",
    "--github-access",
)

PROVIDER_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
MODEL_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:+/@-]{0,255}$")
ENVIRONMENT_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")

OPENCODE_LOCAL_ENVIRONMENT = {
    "OPENCODE_DISABLE_AUTOUPDATE": "true",
    "OPENCODE_DISABLE_CLAUDE_CODE_PROMPT": "true",
    "OPENCODE_DISABLE_CLAUDE_CODE_SKILLS": "true",
    "OPENCODE_DISABLE_DEFAULT_PLUGINS": "true",
    "OPENCODE_DISABLE_EXTERNAL_SKILLS": "true",
    "OPENCODE_DISABLE_LSP_DOWNLOAD": "true",
    "OPENCODE_DISABLE_MODELS_FETCH": "true",
    "OPENCODE_DISABLE_PROJECT_CONFIG": "true",
    "OPENCODE_DISABLE_SHARE": "true",
    "OPENCODE_EXPERIMENTAL": "false",
    "OPENCODE_EXPERIMENTAL_CODE_MODE": "false",
    "OPENCODE_EXPERIMENTAL_DISABLE_FILEWATCHER": "true",
    "OPENCODE_AUTO_SHARE": "false",
    "OPENCODE_ENABLE_EXA": "true",
    "OPENCODE_DB": ":memory:",
    "OPENCODE_PURE": "true",
}

COPILOT_INHERIT_AGENTS = (
    "grillmester:grillmester",
    "grillmester:barista",
    "grillmester:designer",
    "grillmester:doctor-who",
    "grillmester:kokk",
    "grillmester:grill-inspektor",
    "grillmester:researcher",
)
COPILOT_DISABLED_BUILTIN_SKILLS = (
    "customize-cloud-agent",
    "github-pr-media",
)

SAFE_HOST_ENVIRONMENT = (
    "COLORTERM",
    "LANG",
    "LC_ALL",
    "LOGNAME",
    "SHELL",
    "TERM",
    "TERM_PROGRAM",
    "USER",
)


class LocalModeError(RuntimeError):
    """Raised when a local-model configuration or launch is unsafe."""


def normalize_cli_arguments(arguments: Sequence[str]) -> list[str]:
    """Normalize convenience syntax before the subcommand parser runs."""

    normalized = list(arguments)
    if normalized == ["help"]:
        return ["--help"]
    if not normalized:
        return ["launch"]
    if normalized[0] in {"-h", "--help"} or not normalized[0].startswith("-"):
        return normalized

    index = 0
    run_index: int | None = None
    while index < len(normalized):
        value = normalized[index]
        if value == "run":
            run_index = index
            break
        if value in LOCAL_ROUTABLE_VALUE_OPTIONS:
            index += 2
            continue
        if any(
            value.startswith(f"{option}=")
            for option in LOCAL_ROUTABLE_VALUE_OPTIONS
        ):
            index += 1
            continue
        if value in LOCAL_ROUTABLE_FLAG_OPTIONS:
            index += 1
            continue
        break
    if run_index is None:
        normalized.insert(0, "launch")
        return normalized
    return ["run", *normalized[:run_index], *normalized[run_index + 1 :]]


@dataclass(frozen=True)
class LocalConfig:
    client: str
    agent: str
    context: str
    provider_id: str
    base_url: str
    model_id: str
    context_window: int = DEFAULT_CONTEXT_WINDOW
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
    api_key_env: str | None = None
    api_key_file: Path | None = None

    @property
    def port(self) -> int:
        return _validated_base_url(self.base_url)

    @property
    def qualified_model(self) -> str:
        return f"{self.provider_id}/{self.model_id}"


@dataclass(frozen=True)
class ModelProbe:
    base_url: str
    model_id: str
    advertised_models: tuple[str, ...]


@dataclass(frozen=True, repr=False)
class _ResolvedSecret:
    value: str | None = field(repr=False)


@dataclass(frozen=True, repr=False)
class _ResolvedGithubCapability:
    secret: _ResolvedSecret = field(repr=False)
    executable: Path


@dataclass(frozen=True)
class LocalVersionProbe:
    """Isolated parent environment for the top-level client version gate."""

    environment: Mapping[str, str]
    cplt_arguments: tuple[str, ...]
    trusted_bin: Path
    root: Path


@dataclass(frozen=True)
class RuntimePaths:
    root: Path
    xdg_config: Path
    xdg_cache: Path
    xdg_data: Path
    xdg_state: Path
    copilot_home: Path
    github_config: Path
    trusted_bin: Path


@dataclass(frozen=True)
class LocalLaunch:
    command: tuple[str, ...]
    environment: Mapping[str, str] = field(repr=False)
    payload: Path
    runtime: RuntimePaths
    secret_environment: frozenset[str] = field(repr=False)

    @property
    def redacted_environment(self) -> dict[str, str]:
        return {
            name: "<redacted>" if name in self.secret_environment else value
            for name, value in self.environment.items()
        }


def _absolute_xdg_root(
    environment: Mapping[str, str], name: str, fallback: Path
) -> Path:
    value = environment.get(name)
    root = Path(value).expanduser() if value else fallback
    if not root.is_absolute():
        raise LocalModeError(f"{name} must be an absolute path")
    return root


def _environment_home(environment: Mapping[str, str]) -> Path:
    configured = environment.get("HOME")
    home = Path(configured).expanduser() if configured else Path.home()
    if not home.is_absolute():
        raise LocalModeError("HOME must be an absolute path")
    return home


def _github_config_candidate(raw: str, home: Path) -> Path:
    if raw == "~":
        candidate = home
    elif raw.startswith("~/"):
        candidate = home / raw[2:]
    else:
        candidate = Path(raw)
    if not candidate.is_absolute():
        raise LocalModeError("GitHub CLI config paths must resolve to absolute paths")
    try:
        return candidate.resolve(strict=False)
    except OSError as exc:
        raise LocalModeError(
            f"could not resolve host GitHub CLI config directory {candidate}: {exc}"
        ) from exc


def _host_github_config_candidates(
    environment: Mapping[str, str],
) -> tuple[Path, ...]:
    """Resolve every host gh directory cplt or gh could otherwise discover."""

    home = _environment_home(environment)
    candidates: list[Path] = []
    configured = environment.get("GH_CONFIG_DIR")
    if configured:
        candidates.append(_github_config_candidate(configured, home))
    xdg = environment.get("XDG_CONFIG_HOME")
    if xdg:
        xdg_root = _github_config_candidate(xdg, home)
        candidates.append(_github_config_candidate(str(xdg_root / "gh"), home))
    candidates.append(_github_config_candidate(str(home / ".config" / "gh"), home))
    return tuple(dict.fromkeys(candidates))


def _existing_host_github_config_dirs(
    environment: Mapping[str, str],
) -> tuple[Path, ...]:
    existing: list[Path] = []
    for candidate in _host_github_config_candidates(environment):
        try:
            observed = candidate.stat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise LocalModeError(
                f"could not inspect host GitHub CLI config directory {candidate}: {exc}"
            ) from exc
        if not stat.S_ISDIR(observed.st_mode):
            raise LocalModeError(
                f"host GitHub CLI config path must be a directory: {candidate}"
            )
        existing.append(candidate)
    return tuple(existing)


def config_path(environment: Mapping[str, str] | None = None) -> Path:
    environment = os.environ if environment is None else environment
    home = _environment_home(environment)
    root = _absolute_xdg_root(environment, "XDG_CONFIG_HOME", home / ".config")
    return root / "grillmester" / CONFIG_FILE


def state_root(environment: Mapping[str, str] | None = None) -> Path:
    environment = os.environ if environment is None else environment
    home = _environment_home(environment)
    root = _absolute_xdg_root(
        environment, "XDG_STATE_HOME", home / ".local" / "state"
    )
    return root / "grillmester" / "local"


def _ensure_private_directory(path: Path) -> None:
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        observed = path.lstat()
    except OSError as exc:
        raise LocalModeError(f"could not prepare private directory {path}: {exc}") from exc
    if stat.S_ISLNK(observed.st_mode) or not stat.S_ISDIR(observed.st_mode):
        raise LocalModeError(f"private path must be a non-symlink directory: {path}")
    if hasattr(os, "geteuid") and observed.st_uid != os.geteuid():
        raise LocalModeError(f"private directory is not owned by the current user: {path}")
    try:
        path.chmod(0o700)
    except OSError as exc:
        raise LocalModeError(f"could not make directory private {path}: {exc}") from exc


def _inspect_private_file(path: Path, *, label: str) -> os.stat_result:
    try:
        observed = path.lstat()
    except OSError as exc:
        raise LocalModeError(f"could not inspect {label} at {path}: {exc}") from exc
    if stat.S_ISLNK(observed.st_mode) or not stat.S_ISREG(observed.st_mode):
        raise LocalModeError(f"{label} must be a regular, non-symlink file: {path}")
    if hasattr(os, "geteuid") and observed.st_uid != os.geteuid():
        raise LocalModeError(f"{label} is not owned by the current user: {path}")
    if stat.S_IMODE(observed.st_mode) & 0o077:
        raise LocalModeError(f"{label} must not be accessible by group or others: {path}")
    return observed


def _read_private_bytes(path: Path, *, label: str, limit: int) -> bytes:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise LocalModeError(
                f"{label} must be a regular, non-symlink file: {path}"
            ) from exc
        raise LocalModeError(f"could not open private {label} at {path}: {exc}") from exc
    try:
        observed = os.fstat(descriptor)
        if not stat.S_ISREG(observed.st_mode):
            raise LocalModeError(f"{label} must be a regular, non-symlink file: {path}")
        if hasattr(os, "geteuid") and observed.st_uid != os.geteuid():
            raise LocalModeError(f"{label} is not owned by the current user: {path}")
        if stat.S_IMODE(observed.st_mode) & 0o077:
            raise LocalModeError(
                f"{label} must not be accessible by group or others: {path}"
            )
        if observed.st_nlink != 1:
            raise LocalModeError(f"{label} must not have hard links: {path}")
        if observed.st_size > limit:
            raise LocalModeError(f"{label} exceeds the {limit}-byte limit")
        chunks: list[bytes] = []
        remaining = limit + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(remaining, 8192))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        if len(content) > limit:
            raise LocalModeError(f"{label} exceeds the {limit}-byte limit")
        return content
    finally:
        os.close(descriptor)


def _atomic_private_write(path: Path, content: bytes) -> None:
    _ensure_private_directory(path.parent)
    try:
        existing = path.lstat()
    except FileNotFoundError:
        existing = None
    except OSError as exc:
        raise LocalModeError(f"could not inspect local state file {path}: {exc}") from exc
    if existing is not None and (
        stat.S_ISLNK(existing.st_mode) or not stat.S_ISREG(existing.st_mode)
    ):
        raise LocalModeError(f"refusing to replace a non-regular state file: {path}")

    descriptor = -1
    temporary: Path | None = None
    try:
        descriptor, raw_temporary = tempfile.mkstemp(
            prefix=f".{path.name}.", dir=str(path.parent)
        )
        temporary = Path(raw_temporary)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            descriptor = -1
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
        path.chmod(0o600)
        try:
            directory_descriptor = os.open(path.parent, os.O_RDONLY)
        except OSError:
            directory_descriptor = -1
        if directory_descriptor >= 0:
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
    except OSError as exc:
        raise LocalModeError(f"could not write private local state {path}: {exc}") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def _validated_base_url(value: str) -> int:
    if not isinstance(value, str) or not value or value != value.strip():
        raise LocalModeError("baseUrl must be a non-empty URL without surrounding space")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise LocalModeError(f"baseUrl has an invalid port: {value!r}") from exc
    if parsed.scheme != "http":
        raise LocalModeError("baseUrl must use http for an explicit loopback endpoint")
    if parsed.username is not None or parsed.password is not None:
        raise LocalModeError("baseUrl must not contain credentials")
    if not parsed.hostname or port is None or not 1 <= port <= 65535:
        raise LocalModeError("baseUrl must contain an explicit port in 1..65535")
    if parsed.path != "/v1" or parsed.query or parsed.fragment:
        raise LocalModeError("baseUrl must end at exactly /v1 without query or fragment")
    hostname = parsed.hostname.lower()
    if hostname != "localhost":
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError as exc:
            raise LocalModeError(
                "baseUrl host must be localhost or a literal loopback address"
            ) from exc
        if not address.is_loopback:
            raise LocalModeError("baseUrl must use a loopback address")
    return port


def _validate_private_key_file(path: Path) -> Path:
    if not path.is_absolute():
        raise LocalModeError("apiKeyFile must be an absolute path")
    observed = _inspect_private_file(path, label="apiKeyFile")
    if observed.st_nlink != 1:
        raise LocalModeError(f"apiKeyFile must not have hard links: {path}")
    if observed.st_size > MAX_SECRET_BYTES:
        raise LocalModeError(f"apiKeyFile exceeds the {MAX_SECRET_BYTES}-byte limit")
    try:
        resolved = path.resolve(strict=True)
        resolved_observed = resolved.stat()
    except OSError as exc:
        raise LocalModeError(f"could not resolve apiKeyFile at {path}: {exc}") from exc
    if (resolved_observed.st_dev, resolved_observed.st_ino) != (
        observed.st_dev,
        observed.st_ino,
    ):
        raise LocalModeError("apiKeyFile identity changed while it was inspected")
    return resolved


def validate_config(config: LocalConfig, *, check_key_file: bool = True) -> LocalConfig:
    if config.client not in CLIENTS:
        raise LocalModeError("client must be opencode or copilot")
    if config.context not in CONTEXTS:
        raise LocalModeError("context must be focused or full")
    if config.agent not in PUBLIC_AGENTS:
        raise LocalModeError(f"unsupported public agent: {config.agent!r}")
    if config.context == "focused" and config.agent != FOCUSED_AGENT:
        raise LocalModeError(
            "focused context supports only the barista agent; use --full for "
            "another agent"
        )
    if not PROVIDER_ID_PATTERN.fullmatch(config.provider_id):
        raise LocalModeError(
            "providerId must start with a lowercase letter and contain only "
            "lowercase letters, digits, '_' or '-'"
        )
    if not MODEL_ID_PATTERN.fullmatch(config.model_id):
        raise LocalModeError("modelId contains unsupported characters or length")
    if (
        type(config.context_window) is not int
        or config.context_window < MINIMUM_CONTEXT_WINDOW
    ):
        raise LocalModeError(
            f"contextWindow must be an integer of at least {MINIMUM_CONTEXT_WINDOW}"
        )
    if (
        type(config.max_output_tokens) is not int
        or config.max_output_tokens <= 0
        or config.max_output_tokens >= config.context_window
    ):
        raise LocalModeError(
            "maxOutputTokens must be a positive integer smaller than contextWindow"
        )
    _validated_base_url(config.base_url)
    if config.api_key_env is not None and config.api_key_file is not None:
        raise LocalModeError("configure at most one of apiKeyEnv and apiKeyFile")
    if config.client == "opencode" and (
        config.api_key_env is not None or config.api_key_file is not None
    ):
        raise LocalModeError(
            "authenticated local providers are not supported with OpenCode because "
            "its tool subprocesses inherit provider environment; use a key-free "
            "loopback server or select --client copilot"
        )
    if config.api_key_env is not None and not ENVIRONMENT_NAME_PATTERN.fullmatch(
        config.api_key_env
    ):
        raise LocalModeError("apiKeyEnv is not a valid environment variable name")
    if config.api_key_env in SAFE_HOST_ENVIRONMENT:
        raise LocalModeError(
            "apiKeyEnv conflicts with a host environment variable preserved for "
            "the terminal client; choose a dedicated secret variable name"
        )
    if config.api_key_file is not None:
        if not config.api_key_file.is_absolute():
            raise LocalModeError("apiKeyFile must be an absolute path")
        if check_key_file:
            config = replace(
                config,
                api_key_file=_validate_private_key_file(config.api_key_file),
            )
        else:
            config = replace(
                config,
                api_key_file=Path(os.path.abspath(config.api_key_file)),
            )
    return config


def _config_object(config: LocalConfig) -> dict[str, object]:
    result: dict[str, object] = {
        "schemaVersion": CONFIG_SCHEMA_VERSION,
        "client": config.client,
        "agent": config.agent,
        "context": config.context,
        "providerId": config.provider_id,
        "baseUrl": config.base_url,
        "modelId": config.model_id,
        "contextWindow": config.context_window,
        "maxOutputTokens": config.max_output_tokens,
    }
    if config.api_key_env is not None:
        result["apiKeyEnv"] = config.api_key_env
    if config.api_key_file is not None:
        result["apiKeyFile"] = str(config.api_key_file)
    return result


def save_config(
    config: LocalConfig,
    path: Path | None = None,
    *,
    environment: Mapping[str, str] | None = None,
) -> Path:
    config = validate_config(config)
    path = path or config_path(environment)
    if not path.is_absolute():
        raise LocalModeError("local config path must be absolute")
    content = (json.dumps(_config_object(config), indent=2) + "\n").encode("utf-8")
    _atomic_private_write(path, content)
    return path


def load_config(
    path: Path | None = None,
    *,
    environment: Mapping[str, str] | None = None,
) -> LocalConfig:
    path = path or config_path(environment)
    try:
        raw = json.loads(
            _read_private_bytes(
                path, label="local config", limit=MAX_CONFIG_BYTES
            )
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LocalModeError(f"local config is not valid UTF-8 JSON: {path}") from exc
    if not isinstance(raw, dict):
        raise LocalModeError("local config must be a JSON object")
    common = {
        "schemaVersion",
        "client",
        "agent",
        "context",
        "providerId",
        "baseUrl",
        "modelId",
        "contextWindow",
        "maxOutputTokens",
    }
    observed_fields = set(raw)
    schema_version = raw.get("schemaVersion")
    if type(schema_version) is not int or schema_version != CONFIG_SCHEMA_VERSION:
        raise LocalModeError("local config uses an unsupported schemaVersion")
    if observed_fields not in (
        common,
        common | {"apiKeyEnv"},
        common | {"apiKeyFile"},
    ):
        raise LocalModeError("local config has unexpected or missing fields")
    string_fields = ("client", "agent", "context", "providerId", "baseUrl", "modelId")
    if any(not isinstance(raw.get(name), str) for name in string_fields):
        raise LocalModeError("local config fields must be strings")
    api_key_env = raw.get("apiKeyEnv")
    api_key_file = raw.get("apiKeyFile")
    if api_key_env is not None and not isinstance(api_key_env, str):
        raise LocalModeError("apiKeyEnv must be a string")
    if api_key_file is not None and not isinstance(api_key_file, str):
        raise LocalModeError("apiKeyFile must be a string path")
    config = LocalConfig(
        client=raw["client"],
        agent=raw["agent"],
        context=raw["context"],
        provider_id=raw["providerId"],
        base_url=raw["baseUrl"],
        model_id=raw["modelId"],
        context_window=raw["contextWindow"],
        max_output_tokens=raw["maxOutputTokens"],
        api_key_env=api_key_env,
        api_key_file=Path(api_key_file) if api_key_file is not None else None,
    )
    return validate_config(config)


def _read_secret(
    config: LocalConfig, environment: Mapping[str, str]
) -> str | None:
    value: str | None
    label: str
    if config.api_key_env is not None:
        label = f"environment variable {config.api_key_env}"
        value = environment.get(config.api_key_env)
        if value is None:
            raise LocalModeError(f"local API key {label} is not set")
    elif config.api_key_file is not None:
        path = config.api_key_file
        if not path.is_absolute():
            raise LocalModeError("apiKeyFile must be an absolute path")
        label = f"file {path}"
        try:
            raw = _read_private_bytes(path, label="apiKeyFile", limit=MAX_SECRET_BYTES)
            value = raw.decode("utf-8").removesuffix("\n")
        except UnicodeDecodeError as exc:
            raise LocalModeError(f"could not read local API key {label}") from exc
    else:
        return None
    try:
        encoded = value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise LocalModeError(
            f"local API key {label} must contain only visible ASCII"
        ) from exc
    if not value or len(encoded) > MAX_SECRET_BYTES:
        raise LocalModeError(f"local API key {label} is empty or too large")
    if any(not 33 <= byte <= 126 for byte in encoded):
        raise LocalModeError(
            f"local API key {label} must contain only visible ASCII"
        )
    return value


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        raise LocalModeError("local model probe refused an HTTP redirect")


def _advertised_models(
    config: LocalConfig,
    *,
    environment: Mapping[str, str] | None = None,
    timeout: float = DEFAULT_PROBE_TIMEOUT,
    resolved_secret: _ResolvedSecret | None = None,
) -> tuple[str, ...]:
    config = validate_config(config)
    if timeout <= 0 or timeout > 60:
        raise LocalModeError("local model probe timeout must be in (0, 60] seconds")
    environment = os.environ if environment is None else environment
    secret = (
        _read_secret(config, environment)
        if resolved_secret is None
        else resolved_secret.value
    )
    headers = {"Accept": "application/json"}
    if secret is not None:
        headers["Authorization"] = f"Bearer {secret}"
    request = urllib.request.Request(
        f"{config.base_url}/models", headers=headers, method="GET"
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            if response.status != 200:
                raise LocalModeError(
                    f"local model probe returned HTTP status {response.status}"
                )
            payload = response.read(MAX_PROBE_BYTES + 1)
    except LocalModeError:
        raise
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise LocalModeError(
            f"could not reach local model endpoint {config.base_url}/models: {exc}"
        ) from exc
    except (http.client.HTTPException, UnicodeError, ValueError) as exc:
        raise LocalModeError(
            "local model endpoint returned an invalid HTTP response"
        ) from exc
    if len(payload) > MAX_PROBE_BYTES:
        raise LocalModeError(
            f"local model probe exceeded the {MAX_PROBE_BYTES}-byte response limit"
        )
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LocalModeError("local model probe did not return valid UTF-8 JSON") from exc
    if not isinstance(value, dict) or not isinstance(value.get("data"), list):
        raise LocalModeError("local model probe response must contain a data array")
    models: list[str] = []
    for entry in value["data"]:
        model_id = entry.get("id") if isinstance(entry, dict) else None
        if (
            not isinstance(model_id, str)
            or MODEL_ID_PATTERN.fullmatch(model_id) is None
        ):
            raise LocalModeError("local model probe contains an invalid model entry")
        models.append(model_id)
    if not models:
        raise LocalModeError("local model probe returned no models")
    return tuple(models)


def probe_model(
    config: LocalConfig,
    *,
    environment: Mapping[str, str] | None = None,
    timeout: float = DEFAULT_PROBE_TIMEOUT,
    resolved_secret: _ResolvedSecret | None = None,
) -> ModelProbe:
    models = _advertised_models(
        config,
        environment=environment,
        timeout=timeout,
        resolved_secret=resolved_secret,
    )
    if config.model_id not in models:
        raise LocalModeError(
            f"local endpoint does not advertise exact modelId {config.model_id!r}"
        )
    return ModelProbe(config.base_url, config.model_id, models)


def _runtime_paths(root: Path) -> RuntimePaths:
    xdg = root / "xdg"
    return RuntimePaths(
        root=root,
        xdg_config=xdg / "config",
        xdg_cache=xdg / "cache",
        xdg_data=xdg / "data",
        xdg_state=xdg / "state",
        copilot_home=root / "copilot",
        github_config=xdg / "config" / "gh",
        trusted_bin=root / "trusted-bin",
    )


def _planned_runtime(environment: Mapping[str, str], client: str) -> RuntimePaths:
    try:
        root = (
            state_root(environment) / "sessions" / f"{client}-preview"
        ).resolve(strict=False)
    except OSError as exc:
        raise LocalModeError(f"could not resolve planned local state: {exc}") from exc
    return _runtime_paths(root)


def _process_start_identity(pid: int) -> str | None:
    """Return a stable macOS process-birth fingerprint for PID-reuse defense."""

    if sys.platform != "darwin" or pid <= 0:
        return None
    ps = Path("/bin/ps")
    try:
        observed = ps.stat()
    except OSError:
        return None
    if (
        not stat.S_ISREG(observed.st_mode)
        or not os.access(ps, os.X_OK)
        or (hasattr(os, "geteuid") and observed.st_uid != 0)
    ):
        return None
    try:
        result = subprocess.run(
            [str(ps), "-o", "lstart=", "-p", str(pid)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    raw = result.stdout.strip()
    if result.returncode != 0 or not raw or len(raw) > 128 or b"\n" in raw:
        return None
    try:
        raw.decode("ascii")
    except UnicodeDecodeError:
        return None
    return hashlib.sha256(raw).hexdigest()[:32]


def _session_owner_is_alive(session: Path) -> bool:
    owner = session / SESSION_OWNER_FILE
    try:
        raw = _read_private_bytes(owner, label="local session owner", limit=64)
    except LocalModeError:
        return False
    try:
        fields = raw.decode("ascii").split()
        pid = int(fields[0])
    except (UnicodeDecodeError, ValueError, IndexError):
        return False
    if pid <= 0 or len(fields) not in (1, 2):
        return False
    start_identity = fields[1] if len(fields) == 2 else None
    if start_identity is not None and re.fullmatch(r"[0-9a-f]{32}", start_identity) is None:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True
    if start_identity is None:
        # Legacy owner files had only a PID. Retain a live match
        # conservatively; newly created sessions always add birth identity on
        # supported macOS hosts.
        return True
    observed_identity = _process_start_identity(pid)
    return observed_identity is None or observed_identity == start_identity


def _prune_inactive_sessions(
    session_parent: Path,
    *,
    retain: int = RETAINED_INACTIVE_SESSIONS,
) -> None:
    """Bound retained local state without touching live or unknown entries."""

    if isinstance(retain, bool) or not isinstance(retain, int) or retain < 0:
        raise LocalModeError("inactive session retention must be a non-negative integer")

    try:
        entries = sorted(session_parent.iterdir(), key=lambda path: path.name)
    except OSError as exc:
        raise LocalModeError(
            f"could not enumerate private local sessions {session_parent}: {exc}"
        ) from exc
    inactive: list[tuple[int, Path]] = []
    for candidate in entries:
        if not re.fullmatch(r"(?:copilot|opencode)-[A-Za-z0-9_]+", candidate.name):
            continue
        try:
            observed = candidate.lstat()
        except FileNotFoundError:
            # Another launch may have pruned the same inactive session after
            # this process enumerated the directory.
            continue
        except OSError as exc:
            raise LocalModeError(
                f"could not inspect private local session {candidate}: {exc}"
            ) from exc
        if stat.S_ISLNK(observed.st_mode) or not stat.S_ISDIR(observed.st_mode):
            # Symlinks and non-directories are never pruned or reused; leaving
            # them alone keeps one odd entry from blocking every launch.
            continue
        if hasattr(os, "geteuid") and observed.st_uid != os.geteuid():
            continue
        if _session_owner_is_alive(candidate):
            continue
        inactive.append((observed.st_mtime_ns, candidate))

    inactive.sort(reverse=True)
    for _, candidate in inactive[retain:]:
        try:
            _remove_owned_session_tree(candidate)
        except FileNotFoundError:
            # Concurrent pruning has already achieved the intended state.
            continue
        except OSError as exc:
            raise LocalModeError(
                f"could not remove stale private local session {candidate}: {exc}"
            ) from exc


def _remove_owned_session_tree(session: Path) -> None:
    """Remove one user-owned session, including legacy sealed directories.

    Early local-launcher builds staged binaries below mode-0500 directories.
    A normal ``shutil.rmtree`` cannot traverse or unlink those trees.  Repair
    permissions only inside the already validated, user-owned session and
    never follow a symlink while doing so.
    """

    def repair_and_retry(function: object, raw_path: str, _error: object) -> None:
        path = Path(raw_path)
        try:
            observed = path.lstat()
        except FileNotFoundError:
            return
        if hasattr(os, "geteuid") and observed.st_uid != os.geteuid():
            raise PermissionError(f"refusing to change foreign session entry {path}")

        parent = path.parent
        try:
            parent_observed = parent.lstat()
        except FileNotFoundError:
            return
        if (
            stat.S_ISDIR(parent_observed.st_mode)
            and not stat.S_ISLNK(parent_observed.st_mode)
            and (
                not hasattr(os, "geteuid")
                or parent_observed.st_uid == os.geteuid()
            )
        ):
            os.chmod(parent, 0o700, follow_symlinks=False)

        if stat.S_ISDIR(observed.st_mode) and not stat.S_ISLNK(observed.st_mode):
            os.chmod(path, 0o700, follow_symlinks=False)
        retry = function
        if not callable(retry):
            raise TypeError("session cleanup callback is not callable")
        retry(raw_path)

    shutil.rmtree(session, onerror=repair_and_retry)


def _session_lock_descriptor(session_parent: Path) -> int:
    """Open and exclusively lock the private create/prune transaction file."""

    lock = session_parent / ".create-prune.lock"
    flags = os.O_RDWR | os.O_CREAT
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(lock, flags, 0o600)
        observed = os.fstat(descriptor)
        if (
            not stat.S_ISREG(observed.st_mode)
            or observed.st_nlink != 1
            or (hasattr(os, "geteuid") and observed.st_uid != os.geteuid())
        ):
            raise LocalModeError(
                f"local session lock must be a user-owned regular file: {lock}"
            )
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        return descriptor
    except BaseException:
        if "descriptor" in locals():
            os.close(descriptor)
        raise


def _prepare_runtime(environment: Mapping[str, str], client: str) -> RuntimePaths:
    session_parent = state_root(environment) / "sessions"
    _ensure_private_directory(session_parent)
    lock_descriptor = _session_lock_descriptor(session_parent)
    root: Path | None = None
    try:
        # Make room for the session being created. Once its cplt process exits,
        # the new root becomes the second retained inactive session rather than
        # temporarily leaving three completed binary copies at rest.
        _prune_inactive_sessions(
            session_parent,
            retain=max(0, RETAINED_INACTIVE_SESSIONS - 1),
        )
        root = Path(tempfile.mkdtemp(prefix=f"{client}-", dir=session_parent))
        root.chmod(0o700)
        # Claim the session while create/prune is still serialized. A second
        # launch can never observe this root in the ownerless interval.
        owner_pid = os.getpid()
        start_identity = _process_start_identity(owner_pid)
        owner_text = (
            f"{owner_pid} {start_identity}\n"
            if start_identity is not None
            else f"{owner_pid}\n"
        )
        _atomic_private_write(
            root / SESSION_OWNER_FILE, owner_text.encode("ascii")
        )
    except OSError as exc:
        raise LocalModeError(f"could not create private local session: {exc}") from exc
    finally:
        try:
            fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
        finally:
            os.close(lock_descriptor)
    assert root is not None
    # Canonical paths matter to Seatbelt's mmap/exec rules on macOS, where
    # /var is an alias of /private/var. Use one physical spelling everywhere.
    try:
        root = root.resolve(strict=True)
    except OSError as exc:
        raise LocalModeError(f"could not canonicalize private local state {root}: {exc}") from exc
    runtime = _runtime_paths(root)
    for directory in (
        runtime.xdg_config.parent,
        runtime.xdg_config,
        runtime.xdg_cache,
        runtime.xdg_data,
        runtime.xdg_state,
        runtime.copilot_home,
        runtime.github_config,
        runtime.trusted_bin,
    ):
        _ensure_private_directory(directory)
    return runtime


def _binary_path(
    value: object, *, label: str, expected_name: str | None = None
) -> Path:
    raw = getattr(value, "path", value)
    if not isinstance(raw, (str, os.PathLike)):
        raise LocalModeError(f"{label} path was not supplied by the caller")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise LocalModeError(f"{label} path must be absolute")
    try:
        resolved = path.resolve(strict=True)
        observed = resolved.stat()
    except OSError as exc:
        raise LocalModeError(f"could not resolve {label} binary {path}: {exc}") from exc
    if not stat.S_ISREG(observed.st_mode) or not os.access(resolved, os.X_OK):
        raise LocalModeError(f"{label} must resolve to an executable regular file")
    if expected_name is not None and resolved.name != expected_name:
        raise LocalModeError(
            f"{label} binary must be named {expected_name!r}; found {resolved.name!r}"
        )
    return resolved


def _binary_detail(
    value: object, *, label: str, expected_name: str | None = None
) -> str:
    """Render a caller-checked binary without executing it again."""

    path = _binary_path(value, label=label, expected_name=expected_name)
    version = getattr(value, "version", None)
    if version is None:
        return str(path)
    if not isinstance(version, str) or not version or any(
        ord(character) < 32 or ord(character) == 127 for character in version
    ):
        raise LocalModeError(f"{label} version detail is not safe to display")
    return f"{path} ({version})"


def _trusted_macos_executable(name: str) -> Path:
    executable = _binary_path(
        Path("/usr/bin") / name,
        label=f"system {name}",
        expected_name=name,
    )
    if hasattr(os, "geteuid") and executable.stat().st_uid != 0:
        raise LocalModeError(f"system {name} must be owned by root")
    return executable


def _prepare_trusted_parent_tools(
    runtime: RuntimePaths,
    *,
    client: Path,
    client_name: str,
    github_executable: Path | None,
) -> None:
    """Keep cplt's parent-side gh/git probes off caller-controlled PATH entries."""

    _ensure_private_directory(runtime.trusted_bin)
    for name in ("git", "sandbox-exec", "uname", "which"):
        executable = _trusted_macos_executable(name)
        try:
            (runtime.trusted_bin / name).symlink_to(executable)
        except OSError as exc:
            raise LocalModeError(
                f"could not prepare trusted system {name}: {exc}"
            ) from exc

    selected_client = _binary_path(
        client, label=client_name
    )
    try:
        (runtime.trusted_bin / client_name).symlink_to(selected_client)
    except OSError as exc:
        raise LocalModeError(f"could not prepare selected {client_name}: {exc}") from exc

    gh_path = runtime.trusted_bin / "gh"
    if github_executable is None:
        _atomic_private_write(gh_path, b"#!/bin/sh\nexit 1\n")
        try:
            gh_path.chmod(0o500)
        except OSError as exc:
            raise LocalModeError(f"could not protect disabled GitHub stub: {exc}") from exc
        return

    gh = _binary_path(
        github_executable, label="GitHub CLI", expected_name="gh"
    )
    try:
        gh_path.symlink_to(gh)
    except OSError as exc:
        raise LocalModeError(f"could not prepare selected GitHub CLI: {exc}") from exc


def _ensure_cplt_executable_state_path(path: Path) -> None:
    """Reject macOS temporary roots where cplt denies process execution."""

    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise LocalModeError(f"could not resolve local executable state {path}: {exc}") from exc
    for raw_root in (Path("/private/tmp"), Path("/private/var/folders")):
        try:
            restricted = raw_root.resolve(strict=True)
        except OSError:
            continue
        if resolved == restricted or resolved.is_relative_to(restricted):
            raise LocalModeError(
                "XDG_STATE_HOME places Grillmester's trusted launch tools below a "
                "macOS temporary directory that cplt cannot execute from; unset "
                "XDG_STATE_HOME or point it to a private directory below your home"
            )


def _resolve_project_directory(project_dir: Path) -> Path:
    try:
        project = project_dir.expanduser().resolve(strict=True)
        observed = project.stat()
    except OSError as exc:
        raise LocalModeError(f"could not resolve local project directory: {exc}") from exc
    if not stat.S_ISDIR(observed.st_mode):
        raise LocalModeError("local project path must be a directory")
    return project


def _resolved_distribution_root(distribution_root: Path) -> Path:
    try:
        distribution = distribution_root.expanduser().resolve(strict=True)
        observed = distribution.stat()
    except OSError as exc:
        raise LocalModeError(
            f"could not resolve Grillmester distribution root: {exc}"
        ) from exc
    if not stat.S_ISDIR(observed.st_mode):
        raise LocalModeError("Grillmester distribution root must be a directory")
    return distribution


def _effective_cplt_config_path(environment: Mapping[str, str]) -> Path:
    configured = environment.get("CPLT_CONFIG")
    home = _environment_home(environment)
    if configured is None:
        return home / ".config" / "cplt" / "config.toml"
    if not configured or "\x00" in configured:
        raise LocalModeError("CPLT_CONFIG must be a non-empty path")
    if configured == "~":
        candidate = home
    elif configured.startswith("~/"):
        candidate = home / configured[2:]
    else:
        candidate = Path(configured)
    if not candidate.is_absolute():
        try:
            candidate = Path.cwd().resolve(strict=True) / candidate
        except OSError as exc:
            raise LocalModeError(f"could not resolve relative CPLT_CONFIG: {exc}") from exc
    return candidate


def _path_is_inside_project(candidate: Path, project: Path) -> bool:
    """Reject lexical or physical overlap with a writable project."""

    if not candidate.is_absolute():
        raise LocalModeError(f"trusted launch path must be absolute: {candidate}")
    lexical = Path(os.path.normpath(str(candidate)))
    try:
        resolved = candidate.resolve(strict=False)
    except OSError as exc:
        raise LocalModeError(f"could not resolve trusted launch path {candidate}: {exc}") from exc
    if any(
        path == project
        or path.is_relative_to(project)
        or project.is_relative_to(path)
        for path in (lexical, resolved)
    ):
        return True

    try:
        resolved_observed = resolved.stat()
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise LocalModeError(
            f"could not inspect trusted launch path {candidate}: {exc}"
        ) from exc
    else:
        if stat.S_ISDIR(resolved_observed.st_mode) and _existing_path_is_within(
            project, resolved
        ):
            return True

    # `Path.resolve()` follows the final symlink and macOS spells `/var` as
    # `/private/var`. Walk the raw path's existing parents by identity as well,
    # so a symlink or prospective file physically located below the project is
    # still rejected even when its target is outside.
    cursor = candidate.parent
    while True:
        try:
            cursor.lstat()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise LocalModeError(
                f"could not inspect trusted launch path parent {cursor}: {exc}"
            ) from exc
        else:
            if _existing_path_is_within(cursor, project):
                return True
        parent = cursor.parent
        if parent == cursor:
            return False
        cursor = parent


def _reject_project_trust_roots(
    project: Path, roots: Sequence[tuple[str, Path]]
) -> None:
    for label, candidate in roots:
        if _path_is_inside_project(candidate, project):
            raise LocalModeError(
                f"{label} must be outside the consumer project because local tools "
                f"can write the project: {candidate}"
            )


def _validate_early_project_trust_roots(
    project_dir: Path, environment: Mapping[str, str]
) -> Path:
    """Validate config/state roots before reading config or preparing a probe."""

    project = _resolve_project_directory(project_dir)
    cplt_config = _effective_cplt_config_path(environment)
    _reject_project_trust_roots(
        project,
        (
            ("Grillmester local config", config_path(environment)),
            ("Grillmester local state", state_root(environment)),
            ("cplt config", cplt_config),
            ("cplt trust directory", cplt_config.parent / "trust"),
        ),
    )
    return project


def _validate_launch_trust_roots(
    *,
    distribution_root: Path,
    project_dir: Path,
    cplt: object,
    client: object,
    client_name: str,
    environment: Mapping[str, str],
    api_key_file: Path | None = None,
    github_executable: Path | None = None,
) -> tuple[Path, Path, Path, Path]:
    """Validate every parent/runtime trust root before writes or execution."""

    project = _validate_early_project_trust_roots(project_dir, environment)
    distribution = _resolved_distribution_root(distribution_root)
    cplt_path = _binary_path(cplt, label="cplt", expected_name="cplt")
    client_path = _binary_path(client, label=client_name)
    roots: list[tuple[str, Path]] = [
        ("Grillmester distribution", distribution),
        ("cplt executable", cplt_path),
        (f"{client_name} executable", client_path),
    ]
    if api_key_file is not None:
        roots.append(("apiKeyFile", api_key_file))
    if github_executable is not None:
        roots.append(("GitHub CLI executable", github_executable))
    _reject_project_trust_roots(project, roots)
    return project, distribution, cplt_path, client_path


def prepare_client_version_probe(
    *,
    client_name: str,
    cplt: object,
    client: object,
    distribution_root: Path,
    project_dir: Path,
    environment: Mapping[str, str] | None = None,
    platform: str | None = None,
) -> LocalVersionProbe:
    """Prepare a credential-free cplt parent before probing a local client."""

    platform = sys.platform if platform is None else platform
    if platform != "darwin":
        raise LocalModeError(
            "the packaged local launcher is currently supported only on macOS"
        )
    if client_name not in CLIENTS:
        raise LocalModeError(f"unsupported local client {client_name!r}")
    source = os.environ if environment is None else environment
    _, _, cplt_path, client_path = _validate_launch_trust_roots(
        distribution_root=distribution_root,
        project_dir=project_dir,
        cplt=cplt,
        client=client,
        client_name=client_name,
        environment=source,
    )
    runtime = _prepare_runtime(source, client_name)
    complete = False
    try:
        _reject_project_trust_roots(
            _resolve_project_directory(project_dir),
            (
                ("Grillmester runtime", runtime.root),
                ("Grillmester trusted tools", runtime.trusted_bin),
            ),
        )
        _ensure_cplt_executable_state_path(runtime.trusted_bin)
        _prepare_trusted_parent_tools(
            runtime,
            client=client_path,
            client_name=client_name,
            github_executable=None,
        )
        sanitized = _sanitized_environment(
            source=source,
            runtime=runtime,
            cplt=cplt_path,
            client_search_directory=client_path.parent,
        )
        passed_environment = [
            "HOME",
            "XDG_CACHE_HOME",
            "XDG_CONFIG_HOME",
            "XDG_DATA_HOME",
            "XDG_STATE_HOME",
            "NO_PROXY",
            "no_proxy",
        ]
        if client_name == "opencode":
            opencode_config = runtime.xdg_config / "opencode"
            _ensure_private_directory(opencode_config)
            sanitized.update(OPENCODE_LOCAL_ENVIRONMENT)
            sanitized.update(
                {
                    "OPENCODE_CONFIG_DIR": str(opencode_config),
                    "OPENCODE_CONFIG_CONTENT": json.dumps(
                        {"autoupdate": False, "share": "disabled"},
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    "OPENCODE_AUTH_CONTENT": "{}",
                }
            )
            passed_environment.extend(
                [
                    "OPENCODE_CONFIG_DIR",
                    "OPENCODE_CONFIG_CONTENT",
                    "OPENCODE_AUTH_CONTENT",
                    *sorted(OPENCODE_LOCAL_ENVIRONMENT),
                ]
            )
        else:
            _atomic_private_write(
                runtime.copilot_home / "settings.json", _copilot_settings()
            )
            sanitized.update(
                {
                    "COPILOT_HOME": str(runtime.copilot_home),
                    "COPILOT_AUTO_UPDATE": "false",
                    "COPILOT_OTEL_ENABLED": "false",
                }
            )
            passed_environment.extend(
                ("COPILOT_HOME", "COPILOT_AUTO_UPDATE", "COPILOT_OTEL_ENABLED")
            )

        cplt_arguments = [
            "--scratch-dir",
            "--deny-clipboard",
            *(
                option
                for option in LOCAL_CPLT_HARDENING_FLAGS
                if option != "--no-audit"
            ),
            "--allow-read",
            str(runtime.trusted_bin),
        ]
        sensitive_paths = list(_existing_host_github_config_dirs(source))
        if client_name == "copilot":
            sensitive_paths.extend(
                _copilot_sensitive_paths(_environment_home(source))
            )
        for sensitive in dict.fromkeys(sensitive_paths):
            cplt_arguments.extend(("--deny-path", str(sensitive)))
        for writable in (
            runtime.xdg_config,
            runtime.xdg_cache,
            runtime.xdg_data,
            runtime.xdg_state,
            runtime.copilot_home,
        ):
            cplt_arguments.extend(("--allow-write", str(writable)))
        for name in dict.fromkeys(passed_environment):
            cplt_arguments.extend(("--pass-env", name))
        probe = LocalVersionProbe(
            sanitized,
            tuple(cplt_arguments),
            runtime.trusted_bin,
            runtime.root,
        )
        complete = True
        return probe
    finally:
        if not complete:
            _remove_owned_session_tree(runtime.root)


def cleanup_client_version_probe(probe: LocalVersionProbe) -> None:
    """Remove the private version-probe session on every parent exit path."""

    if not isinstance(probe, LocalVersionProbe):
        raise LocalModeError("invalid local version-probe cleanup request")
    _remove_owned_session_tree(probe.root)


# cplt owns the sandbox contract. Grillmester only requires the guards and
# forced proxy needed by its connected-local promise. It deliberately does not
# override cplt's domain allow/block policy; user and managed cplt config remain
# authoritative. The exact model endpoint is opened separately below.
LOCAL_CPLT_HARDENING_FLAGS = (
    "--proxy-forced",
    "--gh-guard",
    "--git-guard",
    # cplt's current parent-side audit invokes repository-configured Git
    # helpers outside the sandbox. Keep it off until upstream disables hooks,
    # fsmonitor and repository config for that audit.
    "--no-audit",
)


CLIENT_INSTALL_HINTS = {
    "copilot": "brew install --cask copilot-cli",
    "cplt": "brew install navikt/tap/cplt",
    "opencode": "brew install opencode",
}
RIPGREP_HINT = (
    "rg was not found on PATH; OpenCode's Glob and Grep tools will be "
    "unavailable in this local session. Install ripgrep with: "
    "brew install ripgrep"
)
GITHUB_ACCESS_HELP = (
    "pass a caller-supplied GH_TOKEN to local tools; host gh config and "
    "caller-PATH tools stay isolated, while cplt's gh guard is a soft boundary"
)


def _resolve_path_executable(
    name: str, environment: Mapping[str, str]
) -> Path | None:
    search_path = environment.get("PATH")
    if not search_path:
        return None
    found = shutil.which(name, path=search_path)
    if found is None:
        return None
    try:
        resolved = Path(found).resolve(strict=True)
        observed = resolved.stat()
    except OSError:
        return None
    if not stat.S_ISREG(observed.st_mode) or not os.access(resolved, os.X_OK):
        return None
    return resolved


def _resolve_ripgrep(environment: Mapping[str, str]) -> Path | None:
    return _resolve_path_executable("rg", environment)


def _explicit_github_token(environment: Mapping[str, str]) -> _ResolvedSecret:
    """Read a GitHub capability only after the caller explicitly opts in."""

    token = environment.get(GITHUB_SECRET_ENV)
    if token is None or not token:
        raise LocalModeError(
            "--github-access requires GH_TOKEN in the caller environment; for "
            "example: GH_TOKEN=\"$(gh auth token)\" grillmester local "
            "--github-access"
        )
    try:
        encoded = token.encode("ascii")
    except UnicodeEncodeError as exc:
        raise LocalModeError("GH_TOKEN must contain only ASCII characters") from exc
    if len(encoded) > MAX_GITHUB_TOKEN_BYTES or re.fullmatch(
        r"[A-Za-z0-9_-]+", token
    ) is None:
        raise LocalModeError("GH_TOKEN has an invalid value")
    return _ResolvedSecret(token)


def _explicit_github_capability(
    environment: Mapping[str, str],
) -> _ResolvedGithubCapability:
    token = _explicit_github_token(environment)
    executable = _resolve_path_executable("gh", environment)
    if executable is None:
        raise LocalModeError(
            "--github-access requires GitHub CLI (gh) on PATH; install it with: "
            "brew install gh"
        )
    return _ResolvedGithubCapability(token, executable)


def _client_search_directory(
    client: Path, *, expected_name: str, environment: Mapping[str, str]
) -> Path:
    if client.name == expected_name:
        return client.parent
    for raw_directory in environment.get("PATH", "").split(os.pathsep):
        if not raw_directory:
            continue
        candidate = Path(raw_directory) / expected_name
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:
            continue
        if resolved == client and os.access(candidate, os.X_OK):
            return Path(raw_directory).resolve(strict=True)
    raise LocalModeError(
        f"the caller-supplied {expected_name} binary resolves to {client}, but PATH "
        f"has no {expected_name!r} alias for cplt's native agent"
    )


def _physical_repository_root(project: Path) -> tuple[Path, bool]:
    """Find the nearest physical Git root without interpreting repository data."""

    for candidate in (project, *project.parents):
        marker = candidate / ".git"
        try:
            observed = marker.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise LocalModeError(f"could not inspect repository marker {marker}: {exc}") from exc
        if stat.S_ISLNK(observed.st_mode) or not (
            stat.S_ISDIR(observed.st_mode) or stat.S_ISREG(observed.st_mode)
        ):
            raise LocalModeError(f"repository marker must not be a symlink: {marker}")
        return candidate, True
    return project, False


def reject_project_opencode_extensions(project: Path) -> None:
    """Reject OpenCode project components that can override the local binding.

    OpenCode keeps inert dependency metadata in ``.opencode`` during normal
    use, including a generated ``.gitignore``.  Project rules may also coexist
    with Grillmester.  Inspect only the config and component roots OpenCode can
    load; the launch environment separately disables project config and
    external components for the local session.
    """

    root, _ = _physical_repository_root(project)
    if root not in (project, *project.parents):
        raise LocalModeError("OpenCode project is outside its physical repository root")
    directories: list[Path] = []
    cursor = project
    while True:
        directories.append(cursor)
        if cursor == root:
            break
        cursor = cursor.parent
    for directory in reversed(directories):
        for relative in (Path(".claude/skills"), Path(".agents/skills")):
            _reject_nonempty_project_component_root(
                directory / relative, client="OpenCode", component="skill"
            )
        for name in ("opencode.json", "opencode.jsonc"):
            candidate = directory / name
            try:
                observed = candidate.lstat()
            except FileNotFoundError:
                continue
            except OSError as exc:
                raise LocalModeError(f"could not inspect project OpenCode config {candidate}: {exc}") from exc
            if stat.S_ISLNK(observed.st_mode) or not stat.S_ISREG(observed.st_mode):
                raise LocalModeError(f"project OpenCode config is unsafe: {candidate}")
            raise LocalModeError(
                f"local mode refuses auto-discovered project OpenCode config: {candidate}"
            )
        extension_root = directory / ".opencode"
        try:
            observed_root = extension_root.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise LocalModeError(
                f"could not inspect project OpenCode directory {extension_root}: {exc}"
            ) from exc
        if stat.S_ISLNK(observed_root.st_mode) or not stat.S_ISDIR(observed_root.st_mode):
            raise LocalModeError(f"project OpenCode directory is unsafe: {extension_root}")

        for name in ("opencode.json", "opencode.jsonc", "mcp.json"):
            candidate = extension_root / name
            try:
                candidate.lstat()
            except FileNotFoundError:
                continue
            except OSError as exc:
                raise LocalModeError(
                    f"could not inspect project OpenCode config {candidate}: {exc}"
                ) from exc
            raise LocalModeError(
                f"local mode refuses auto-discovered project OpenCode config: {candidate}"
            )

        for name, component in (
            ("agent", "agent"),
            ("agents", "agent"),
            ("command", "command"),
            ("commands", "command"),
            ("mode", "mode"),
            ("modes", "mode"),
            ("plugin", "plugin"),
            ("plugins", "plugin"),
            ("skill", "skill"),
            ("skills", "skill"),
            ("theme", "theme"),
            ("themes", "theme"),
            ("tool", "tool"),
            ("tools", "tool"),
        ):
            _reject_nonempty_project_component_root(
                extension_root / name,
                client="OpenCode",
                component=component,
            )


def _reject_nonempty_project_component_root(
    candidate: Path, *, client: str, component: str
) -> None:
    """Reject a discovery root that could override reviewed payload IDs."""

    try:
        observed = candidate.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise LocalModeError(
            f"could not inspect project {client} {component} root {candidate}: {exc}"
        ) from exc
    if stat.S_ISLNK(observed.st_mode) or not stat.S_ISDIR(observed.st_mode):
        raise LocalModeError(f"project {client} {component} root is unsafe: {candidate}")
    try:
        entries = sorted(candidate.iterdir(), key=lambda entry: entry.name)
    except OSError as exc:
        raise LocalModeError(
            f"could not enumerate project {client} {component} root {candidate}: {exc}"
        ) from exc
    if entries:
        raise LocalModeError(
            f"local mode refuses auto-discovered project {client} {component}: "
            f"{entries[0]}"
        )


def reject_project_copilot_hooks(project: Path) -> None:
    """Reject repo components that can override the reviewed local payload.

    The isolated user settings disable hooks globally, but Copilot repository
    settings, agents, and skills can take precedence. Scan every physical
    directory from the Git root to the selected project so a nested working
    directory cannot bypass the guard.
    """

    root, _ = _physical_repository_root(project)
    if root not in (project, *project.parents):
        raise LocalModeError("Copilot project is outside its physical repository root")
    directories: list[Path] = []
    cursor = project
    while True:
        directories.append(cursor)
        if cursor == root:
            break
        cursor = cursor.parent

    for directory in reversed(directories):
        for relative, component in (
            (Path(".github/agents"), "agent"),
            (Path(".claude/agents"), "agent"),
            (Path(".github/skills"), "skill"),
            (Path(".agents/skills"), "skill"),
            (Path(".claude/skills"), "skill"),
        ):
            _reject_nonempty_project_component_root(
                directory / relative, client="Copilot", component=component
            )
        for relative in (
            Path(".mcp.json"),
            Path(".github/mcp.json"),
            Path(".github/lsp.json"),
            Path(".github/copilot/settings.json"),
            Path(".github/copilot/settings.local.json"),
            Path(".claude/settings.json"),
            Path(".claude/settings.local.json"),
        ):
            candidate = directory / relative
            try:
                candidate.lstat()
            except FileNotFoundError:
                continue
            except OSError as exc:
                raise LocalModeError(
                    f"could not inspect project Copilot executable config {candidate}: {exc}"
                ) from exc
            raise LocalModeError(
                "local mode refuses auto-discovered project Copilot executable config: "
                f"{candidate}"
            )

        extensions = directory / ".github/extensions"
        try:
            observed_extensions = extensions.lstat()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise LocalModeError(
                f"could not inspect project Copilot extensions {extensions}: {exc}"
            ) from exc
        else:
            if stat.S_ISLNK(observed_extensions.st_mode) or not stat.S_ISDIR(
                observed_extensions.st_mode
            ):
                raise LocalModeError(
                    f"project Copilot extensions directory is unsafe: {extensions}"
                )
            try:
                entries = sorted(extensions.iterdir(), key=lambda entry: entry.name)
            except OSError as exc:
                raise LocalModeError(
                    f"could not enumerate project Copilot extensions {extensions}: {exc}"
                ) from exc
            if entries:
                raise LocalModeError(
                    "local mode refuses auto-discovered project Copilot extension: "
                    f"{entries[0]}"
                )

        hooks = directory / ".github/hooks"
        try:
            observed_hooks = hooks.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise LocalModeError(
                f"could not inspect project Copilot hooks {hooks}: {exc}"
            ) from exc
        if stat.S_ISLNK(observed_hooks.st_mode) or not stat.S_ISDIR(
            observed_hooks.st_mode
        ):
            raise LocalModeError(f"project Copilot hooks directory is unsafe: {hooks}")
        try:
            entries = sorted(hooks.iterdir(), key=lambda entry: entry.name)
        except OSError as exc:
            raise LocalModeError(
                f"could not enumerate project Copilot hooks {hooks}: {exc}"
            ) from exc
        for entry in entries:
            if entry.name.casefold().endswith(".json"):
                raise LocalModeError(
                    "local mode refuses auto-discovered project Copilot hook: "
                    f"{entry}"
                )


PAYLOADS = {
    ("opencode", "focused"): (
        Path("targets/opencode-v1-focused"),
        "opencode-v1-focused",
    ),
    ("opencode", "full"): (Path("targets/opencode-v1"), "opencode-v1"),
    ("copilot", "focused"): (
        Path("targets/copilot-cli-focused-v1"),
        "copilot-cli-focused-v1",
    ),
    ("copilot", "full"): (Path("plugin"), "copilot-full-v1"),
}


def _payload_path(root: Path, config: LocalConfig) -> Path:
    relative, expected_target = PAYLOADS[(config.client, config.context)]
    try:
        root = root.expanduser().resolve(strict=True)
        candidate = root / relative
        observed = candidate.lstat()
    except OSError as exc:
        raise LocalModeError(f"local {config.context} payload is unavailable: {relative}") from exc
    if stat.S_ISLNK(observed.st_mode) or not stat.S_ISDIR(observed.st_mode):
        raise LocalModeError(f"local payload must be a non-symlink directory: {candidate}")
    candidate = candidate.resolve(strict=True)
    _verify_manifested_payload(candidate, expected_target=expected_target)
    return candidate


def _read_json_file(path: Path, *, label: str) -> dict[str, object]:
    try:
        observed = path.lstat()
    except OSError as exc:
        raise LocalModeError(f"could not inspect {label} at {path}: {exc}") from exc
    if stat.S_ISLNK(observed.st_mode) or not stat.S_ISREG(observed.st_mode):
        raise LocalModeError(f"{label} must be a regular, non-symlink file: {path}")
    if observed.st_size > 2 * 1024 * 1024:
        raise LocalModeError(f"{label} exceeds the 2 MiB limit")
    try:
        value = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LocalModeError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise LocalModeError(f"{label} must be a JSON object")
    return value


def _verify_manifested_payload(payload: Path, *, expected_target: str) -> None:
    manifest = _read_json_file(payload / "manifest.json", label="local payload manifest")
    if manifest.get("schemaVersion") != 1 or manifest.get("target") != expected_target:
        raise LocalModeError(
            f"local payload manifest does not name {expected_target!r} schema 1"
        )
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise LocalModeError("local payload manifest has no exact files map")
    expected: dict[str, tuple[str, int]] = {}
    for relative, record in files.items():
        if (
            not isinstance(relative, str)
            or not relative
            or relative.startswith("/")
            or ".." in Path(relative).parts
            or not isinstance(record, dict)
            or not isinstance(record.get("sha256"), str)
            or re.fullmatch(r"[0-9a-f]{64}", record["sha256"]) is None
            or record.get("mode") not in {"0644", "0755"}
        ):
            raise LocalModeError("local payload manifest contains an invalid file record")
        expected[relative] = (record["sha256"], int(record["mode"], 8))

    observed_files: set[str] = set()
    stack = [payload]
    while stack:
        directory = stack.pop()
        try:
            children = list(directory.iterdir())
        except OSError as exc:
            raise LocalModeError(f"could not inspect local payload {directory}: {exc}") from exc
        for child in children:
            relative = child.relative_to(payload).as_posix()
            try:
                observed = child.lstat()
            except OSError as exc:
                raise LocalModeError(f"could not inspect local payload entry {child}: {exc}") from exc
            if stat.S_ISLNK(observed.st_mode):
                raise LocalModeError(f"local payload contains a symlink: {child}")
            if stat.S_ISDIR(observed.st_mode):
                stack.append(child)
                continue
            if not stat.S_ISREG(observed.st_mode):
                raise LocalModeError(f"local payload contains a non-regular file: {child}")
            if relative == "manifest.json":
                continue
            observed_files.add(relative)
            record = expected.get(relative)
            if record is None:
                raise LocalModeError(f"local payload has an unmanifested file: {relative}")
            try:
                content = child.read_bytes()
            except OSError as exc:
                raise LocalModeError(f"could not read local payload file {child}: {exc}") from exc
            if hashlib.sha256(content).hexdigest() != record[0]:
                raise LocalModeError(f"local payload digest mismatch: {relative}")
            if stat.S_IMODE(observed.st_mode) != record[1]:
                raise LocalModeError(f"local payload mode mismatch: {relative}")
    if observed_files != set(expected):
        missing = sorted(set(expected) - observed_files)
        raise LocalModeError(f"local payload is missing manifested files: {', '.join(missing)}")


def _opencode_config_content(config: LocalConfig) -> str:
    options: dict[str, object] = {"baseURL": config.base_url}
    value = {
        "autoupdate": False,
        "compaction": {"auto": True},
        "share": "disabled",
        "provider": {
            config.provider_id: {
                "npm": "@ai-sdk/openai-compatible",
                "name": f"Local {config.provider_id}",
                "options": options,
                "models": {
                    config.model_id: {
                        "name": config.model_id,
                        "tool_call": True,
                        "modalities": {"input": ["text"], "output": ["text"]},
                        "limit": {
                            "context": config.context_window,
                            "output": config.max_output_tokens,
                        },
                    }
                },
            }
        },
    }
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _copilot_settings() -> bytes:
    value = {
        "autoUpdate": False,
        "disableAllHooks": True,
        "disabledSkills": list(COPILOT_DISABLED_BUILTIN_SKILLS),
        "experimental": False,
        "ide": {"autoConnect": False},
        "memory": False,
        "subagents": {
            "agents": {name: {"model": "inherit"} for name in COPILOT_INHERIT_AGENTS}
        }
    }
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _sanitized_environment(
    *,
    source: Mapping[str, str],
    runtime: RuntimePaths,
    cplt: Path,
    client_search_directory: Path,
) -> dict[str, str]:
    host_home = _environment_home(source)
    result = {
        name: source[name]
        for name in SAFE_HOST_ENVIRONMENT
        if name in source and "\x00" not in source[name]
    }
    path_entries: list[str] = []
    candidates = [runtime.trusted_bin, client_search_directory, cplt.parent]
    candidates.extend(
        Path(raw)
        for raw in source.get("PATH", "").split(os.pathsep)
        if raw and Path(raw).is_absolute() and "\x00" not in raw
    )
    candidates.extend(
        (Path("/usr/bin"), Path("/bin"), Path("/usr/sbin"), Path("/sbin"))
    )
    for entry in candidates:
        try:
            resolved = entry.resolve(strict=True)
            observed = resolved.stat()
        except OSError:
            continue
        if not stat.S_ISDIR(observed.st_mode) or not os.access(resolved, os.X_OK):
            continue
        rendered = str(resolved)
        if rendered not in path_entries:
            path_entries.append(rendered)
    result.update(
        {
            "PATH": os.pathsep.join(path_entries),
            # cplt, rather than a synthetic HOME, owns host-account isolation.
            # Explicit deny rules below hide raw gh/client state from the
            # child, while client-owned state remains redirected.
            "HOME": str(host_home),
            # Keep cplt's parent-side Copilot token mediation away from the
            # caller's ambient gh account. Explicit --github-access supplies
            # one caller-owned GH_TOKEN instead.
            "GH_CONFIG_DIR": str(runtime.github_config),
            "XDG_CONFIG_HOME": str(runtime.xdg_config),
            "XDG_CACHE_HOME": str(runtime.xdg_cache),
            "XDG_DATA_HOME": str(runtime.xdg_data),
            "XDG_STATE_HOME": str(runtime.xdg_state),
            "NO_PROXY": "127.0.0.1,localhost,::1",
            "no_proxy": "127.0.0.1,localhost,::1",
        }
    )
    cplt_config = source.get("CPLT_CONFIG")
    if cplt_config is not None:
        try:
            canonical_cplt_config = _effective_cplt_config_path(source).resolve(
                strict=False
            )
        except OSError as exc:
            raise LocalModeError(f"could not resolve CPLT_CONFIG: {exc}") from exc
        result["CPLT_CONFIG"] = str(canonical_cplt_config)
    return result


def _copilot_sensitive_paths(home: Path) -> tuple[Path, ...]:
    candidates = (
        home / ".copilot",
        home / ".agents",
        home / ".claude",
        home / ".config" / "github-copilot",
        home / "Library" / "Application Support" / "GitHub Copilot",
    )
    result: list[Path] = []
    for candidate in candidates:
        try:
            candidate.lstat()
            resolved = candidate.resolve(strict=True)
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise LocalModeError(f"could not resolve sensitive Copilot path {candidate}: {exc}") from exc
        if resolved not in result:
            result.append(resolved)
    return tuple(result)


def _existing_path_is_within(candidate: Path, directory: Path) -> bool:
    """Compare existing path ancestry by filesystem identity, not spelling."""

    try:
        directory_observed = directory.stat()
    except OSError as exc:
        raise LocalModeError(f"could not inspect protected directory {directory}: {exc}") from exc
    directory_identity = (directory_observed.st_dev, directory_observed.st_ino)
    cursor = candidate
    while True:
        try:
            observed = cursor.stat()
        except OSError as exc:
            raise LocalModeError(f"could not inspect protected path {cursor}: {exc}") from exc
        if (observed.st_dev, observed.st_ino) == directory_identity:
            return True
        parent = cursor.parent
        if parent == cursor:
            return False
        cursor = parent


def _contains_option(arguments: Sequence[str], option: str) -> bool:
    for argument in arguments:
        if argument == option or argument.startswith(f"{option}="):
            return True
        if (
            option.startswith("-")
            and not option.startswith("--")
            and len(option) == 2
            and argument.startswith(option)
            and len(argument) > len(option)
        ):
            return True
    return False


def _validate_short_option_clusters(client: str, arguments: Sequence[str]) -> None:
    """Reject owned short options hidden inside a client short-option cluster.

    Both supported clients accept clusters such as ``-sv``.  Stop parsing once
    a value-taking option is reached so values such as ``-pMODEL`` remain data,
    not additional flags.  Unknown cluster members fail closed because their
    value/boolean semantics cannot be established safely.
    """

    if client == "opencode":
        boolean_options = frozenset({"h", "v"})
        value_options = frozenset()
        owned_options = frozenset({"c", "m", "p", "s", "u"})
    else:
        boolean_options = frozenset({"h", "s", "v"})
        value_options = frozenset({"i", "n", "p"})
        owned_options = frozenset({"C", "m", "r", "w"})

    for index, argument in enumerate(arguments):
        if not argument.startswith("-") or argument.startswith("--") or argument == "-":
            continue
        cluster = argument[1:]
        for position, member in enumerate(cluster):
            if member in owned_options:
                raise LocalModeError(f"client option -{member} is owned by local mode")
            if member in value_options:
                if position == len(cluster) - 1 and index + 1 >= len(arguments):
                    raise LocalModeError(
                        f"client option -{member} needs a value in local mode"
                    )
                break
            if member not in boolean_options:
                raise LocalModeError(
                    f"unknown short option -{member} in {argument!r}; "
                    "local mode accepts only reviewed client options"
                )


def _validate_client_arguments(client: str, arguments: Sequence[str]) -> None:
    if any("\x00" in argument for argument in arguments):
        raise LocalModeError("client arguments must not contain NUL bytes")
    if client == "opencode" and arguments and arguments[0] == "run":
        raise LocalModeError(
            "OpenCode task execution must use 'grillmester local run'; "
            "that explicit mode auto-approves tools and project writes"
        )
    _validate_short_option_clusters(client, arguments)
    owned = {"--agent", "--model", "-m"}
    if client == "opencode":
        owned.update(
            {
                "--attach",
                "--auto",
                "--command",
                "--continue",
                "--cors",
                "--dangerously-skip-permissions",
                "--dir",
                "--fork",
                "--hostname",
                "--mdns",
                "--mdns-domain",
                "--password",
                "--port",
                "--prompt",
                "--session",
                "--share",
                "--username",
                "--yolo",
            }
        )
    if client == "copilot":
        owned.update(
            {
                "-C",
                "--add-dir",
                "--add-github-mcp-tool",
                "--add-github-mcp-toolset",
                "--additional-mcp-config",
                "--allow-all",
                "--allow-all-mcp-server-instructions",
                "--allow-all-paths",
                "--allow-all-tools",
                "--allow-all-urls",
                "--allow-tool",
                "--allow-url",
                "--acp",
                "--plugin-dir",
                "--autopilot",
                "--bash-env",
                "--connect",
                "--config-dir",
                "--continue",
                "--enable-all-github-mcp-tools",
                "--enable-memory",
                "--embedded-host",
                "--experimental",
                "--extension-sdk-path",
                "--headless",
                "--log-dir",
                "--max-autopilot-continues",
                "--mode",
                "--remote",
                "--remote-export",
                "--no-remote",
                "--no-remote-export",
                "--auto-update",
                "--no-auto-update",
                "--no-experimental",
                "--disable-builtin-mcps",
                "--enable-builtin-mcps",
                "--secret-env-vars",
                "--server",
                "--session-id",
                "--share",
                "--share-gist",
                "--resume",
                "-r",
                "--yolo",
            }
        )
    for option in sorted(owned):
        if _contains_option(arguments, option):
            raise LocalModeError(f"client option {option} is owned by local mode")
    if client == "opencode":
        _validate_opencode_option_allowlist(arguments)
    if client == "copilot":
        _validate_copilot_option_allowlist(arguments)
        _reject_copilot_command_mode(arguments)


def _validate_opencode_option_allowlist(arguments: Sequence[str]) -> None:
    """Allow only the reviewed OpenCode 1.18.20 interactive option surface."""

    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument == "--":
            raise LocalModeError(
                "local OpenCode launch accepts the TUI, --help, or --version; "
                "use 'grillmester local run' for an auto-approved task, or the "
                "system OpenCode command for other modes"
            )
        if not argument.startswith("-") or argument == "-":
            # Outside run, a positional would select an OpenCode command or
            # an unscanned project directory.
            raise LocalModeError(
                "local OpenCode launch accepts the TUI, --help, or --version; "
                "use 'grillmester local run' for an auto-approved task, or the "
                "system OpenCode command for other modes"
            )
        if not argument.startswith("--"):
            # Exact short boolean options and clusters were fully classified
            # above. OpenCode's root/TUI surface has no safe short value option.
            index += 1
            continue
        name, separator, value = argument.partition("=")
        if name in OPENCODE_SAFE_BOOLEAN_OPTIONS:
            if separator:
                raise LocalModeError(
                    f"client option {name} does not accept an attached value in local mode"
                )
            index += 1
            continue
        if name in OPENCODE_SAFE_VALUE_OPTIONS:
            if separator:
                if not value:
                    raise LocalModeError(
                        f"client option {name} needs a non-empty value in local mode"
                    )
                index += 1
                continue
            if index + 1 >= len(arguments):
                raise LocalModeError(
                    f"client option {name} needs a value in local mode"
                )
            index += 2
            continue
        raise LocalModeError(
            f"client option {name} is not supported by local mode; "
            "run the system opencode command directly for other modes"
        )


def _validate_copilot_option_allowlist(arguments: Sequence[str]) -> None:
    """Reject undocumented/future Copilot modes until they are reviewed."""

    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument == "--":
            index += 1
            continue
        if not argument.startswith("-") or argument == "-":
            index += 1
            continue
        if not argument.startswith("--"):
            # Short options and clusters were classified above against the
            # exact 1.0.80 boolean/value roster.
            index += 1
            continue
        name, separator, value = argument.partition("=")
        if name in COPILOT_SAFE_BOOLEAN_OPTIONS:
            if separator:
                raise LocalModeError(
                    f"client option {name} does not accept an attached value in local mode"
                )
            index += 1
            continue
        if name in COPILOT_SAFE_OPTIONAL_VALUE_OPTIONS:
            # Copilot documents these as --option[=values...]. A separate
            # token is deliberately not consumed, so command-mode detection
            # cannot be hidden behind an ambiguous optional argument.
            index += 1
            continue
        if name in COPILOT_SAFE_VALUE_OPTIONS:
            if separator:
                if not value:
                    raise LocalModeError(
                        f"client option {name} needs a non-empty value in local mode"
                    )
                index += 1
                continue
            if index + 1 >= len(arguments):
                raise LocalModeError(
                    f"client option {name} needs a value in local mode"
                )
            index += 2
            continue
        raise LocalModeError(
            f"client option {name} is not supported by local mode; "
            "run the system copilot command directly for other modes"
        )


def _reject_copilot_command_mode(arguments: Sequence[str]) -> None:
    """Keep local Copilot in a fresh TUI or prompt session.

    Copilot's admin commands are accepted after global options.  Parse only the
    documented, allowed value-taking options so a prompt value is not mistaken
    for a command.  Any remaining positional token is command mode and fails
    closed, except the two side-effect-free metadata commands.
    """

    if tuple(arguments) in COPILOT_SAFE_META_ARGUMENTS:
        return
    short_value_options = frozenset({"i", "n", "p"})
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument == "--":
            if index + 1 < len(arguments):
                raise LocalModeError(
                    "local Copilot does not accept command-mode positional arguments; "
                    "run the system copilot command directly for admin commands"
                )
            return
        if argument.startswith("--"):
            name, separator, _ = argument.partition("=")
            if not separator and name in COPILOT_SAFE_VALUE_OPTIONS:
                index += 2
            else:
                index += 1
            continue
        if argument.startswith("-") and argument != "-":
            if len(argument) == 2 and argument[1] in short_value_options:
                index += 2
                continue
            cluster = argument[1:]
            value_index = next(
                (
                    position
                    for position, member in enumerate(cluster)
                    if member in short_value_options
                ),
                None,
            )
            if value_index is not None and value_index == len(cluster) - 1:
                index += 2
            else:
                index += 1
            continue
        raise LocalModeError(
            "local Copilot does not accept command-mode positional arguments; "
            "run the system copilot command directly for admin commands"
        )


def _copilot_binding_arguments(
    config: LocalConfig, payload: Path, *, github_access: bool = False
) -> list[str]:
    secret_environment = [
        COPILOT_SECRET_ENV,
        *COPILOT_GITHUB_SECRET_ENVIRONMENTS,
    ]
    if not github_access:
        secret_environment.insert(1, "GH_TOKEN")
    return [
        "--plugin-dir",
        str(payload),
        "--agent",
        f"grillmester:{config.agent}",
        "--model",
        config.model_id,
        "--effort",
        DEFAULT_COPILOT_REASONING_EFFORT,
        "--no-auto-update",
        "--no-experimental",
        "--no-remote",
        "--no-remote-export",
        "--disable-builtin-mcps",
        f"--secret-env-vars={','.join(secret_environment)}",
    ]


def _validate_run_prompt(run_prompt: str) -> None:
    if "\x00" in run_prompt:
        raise LocalModeError("local run prompt must not contain NUL bytes")
    if not run_prompt.strip():
        raise LocalModeError("local run prompt must not be empty")


def _client_arguments(
    config: LocalConfig,
    payload: Path,
    arguments: Sequence[str],
    *,
    run_prompt: str | None = None,
    github_access: bool = False,
) -> list[str]:
    if run_prompt is not None:
        if arguments:
            raise LocalModeError(
                "local run owns the client command line and accepts only one prompt"
            )
        _validate_run_prompt(run_prompt)
        if config.client == "opencode":
            return [
                "run",
                "--agent",
                config.agent,
                "--model",
                config.qualified_model,
                "--auto",
                "--title",
                "Grillmester local run",
                "--",
                run_prompt,
            ]
        return [
            *_copilot_binding_arguments(
                config, payload, github_access=github_access
            ),
            "--prompt",
            run_prompt,
            "--allow-all-tools",
            "--allow-all-urls",
            "--no-ask-user",
            *([] if github_access else ["--deny-tool=shell(gh:*)"]),
        ]
    _validate_client_arguments(config.client, arguments)
    if config.client == "opencode":
        binding = ["--agent", config.agent, "--model", config.qualified_model]
        if not arguments:
            return binding
        if tuple(arguments) in OPENCODE_SAFE_META_ARGUMENTS:
            return list(arguments)
        if arguments[0].startswith("-"):
            return [*binding, *arguments]
        raise LocalModeError(
            "local OpenCode launch accepts the TUI, --help, or --version; use "
            "'grillmester local run' for an auto-approved task, or the system "
            "OpenCode command for admin commands or another project"
        )
    return [
        *_copilot_binding_arguments(config, payload, github_access=github_access),
        *arguments,
    ]


def build_local_launch(
    config: LocalConfig,
    *,
    distribution_root: Path,
    project_dir: Path,
    cplt: object,
    client: object,
    client_arguments: Sequence[str] = (),
    run_prompt: str | None = None,
    environment: Mapping[str, str] | None = None,
    github_access: bool = False,
    resolve_credentials: bool = True,
    resolved_secret: _ResolvedSecret | None = None,
    resolved_github_capability: _ResolvedGithubCapability | None = None,
    prepare_state: bool = True,
    platform: str | None = None,
) -> LocalLaunch:
    """Build one cplt-backed local-inference command without executing it."""

    platform = sys.platform if platform is None else platform
    if platform != "darwin":
        raise LocalModeError(
            "the packaged local launcher is currently supported only on macOS"
        )
    source_environment = os.environ if environment is None else environment
    config = validate_config(config, check_key_file=resolve_credentials)
    project = _resolve_project_directory(project_dir)
    if (
        resolve_credentials
        and config.api_key_file is not None
        and _existing_path_is_within(config.api_key_file, project)
    ):
        raise LocalModeError(
            "apiKeyFile must be outside the consumer project so the sandboxed "
            "client can never read the original credential file"
        )
    if config.client == "opencode":
        reject_project_opencode_extensions(project)
    else:
        reject_project_copilot_hooks(project)
    github_secret: str | None = None
    github_executable: Path | None = None
    if github_access:
        if resolve_credentials:
            capability = (
                _explicit_github_capability(source_environment)
                if resolved_github_capability is None
                else resolved_github_capability
            )
            github_secret = capability.secret.value
            github_executable = capability.executable
        else:
            github_secret = "<redacted>"
    project, distribution, cplt_path, client_path = _validate_launch_trust_roots(
        distribution_root=distribution_root,
        project_dir=project,
        cplt=cplt,
        client=client,
        client_name=config.client,
        environment=source_environment,
        api_key_file=config.api_key_file,
        github_executable=github_executable,
    )
    payload = _payload_path(distribution, config)
    secret_configured = config.api_key_env is not None or config.api_key_file is not None
    if not resolve_credentials:
        secret = None
    elif resolved_secret is None:
        secret = _read_secret(config, source_environment)
    else:
        secret = resolved_secret.value
    runtime = (
        _prepare_runtime(source_environment, config.client)
        if prepare_state
        else _planned_runtime(source_environment, config.client)
    )
    _reject_project_trust_roots(
        project,
        (
            ("Grillmester runtime", runtime.root),
            ("Grillmester trusted tools", runtime.trusted_bin),
        ),
    )
    if prepare_state:
        _ensure_cplt_executable_state_path(runtime.trusted_bin)
        _prepare_trusted_parent_tools(
            runtime,
            client=client_path,
            client_name=config.client,
            github_executable=github_executable if github_access else None,
        )
    launch_cplt_path = cplt_path
    client_search_directory = _client_search_directory(
        client_path,
        expected_name=config.client,
        environment=source_environment,
    )
    child_environment = _sanitized_environment(
        source=source_environment,
        runtime=runtime,
        cplt=launch_cplt_path,
        client_search_directory=client_search_directory,
    )
    passed_environment = [
        "HOME",
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_STATE_HOME",
        "NO_PROXY",
        "no_proxy",
    ]
    if config.client == "opencode":
        child_environment.update(OPENCODE_LOCAL_ENVIRONMENT)
        child_environment["OPENCODE_CONFIG_DIR"] = str(payload)
        child_environment["OPENCODE_CONFIG_CONTENT"] = _opencode_config_content(config)
        child_environment["OPENCODE_AUTH_CONTENT"] = "{}"
        passed_environment.extend(
            [
                "OPENCODE_CONFIG_DIR",
                "OPENCODE_CONFIG_CONTENT",
                "OPENCODE_AUTH_CONTENT",
                *sorted(OPENCODE_LOCAL_ENVIRONMENT),
            ]
        )
        secret_names = frozenset()
    else:
        if prepare_state:
            _atomic_private_write(
                runtime.copilot_home / "settings.json", _copilot_settings()
            )
        child_environment.update(
            {
                "COPILOT_HOME": str(runtime.copilot_home),
                "COPILOT_PROVIDER_TYPE": "openai",
                "COPILOT_PROVIDER_BASE_URL": config.base_url,
                "COPILOT_PROVIDER_API_KEY": (
                    secret
                    if resolve_credentials and secret is not None
                    else "<redacted>"
                    if secret_configured
                    else "local"
                ),
                "COPILOT_PROVIDER_WIRE_API": "completions",
                "COPILOT_PROVIDER_MODEL_ID": config.model_id,
                "COPILOT_PROVIDER_WIRE_MODEL": config.model_id,
                "COPILOT_PROVIDER_MAX_PROMPT_TOKENS": str(
                    config.context_window - config.max_output_tokens
                ),
                "COPILOT_PROVIDER_MAX_OUTPUT_TOKENS": str(
                    config.max_output_tokens
                ),
                "COPILOT_MODEL": config.model_id,
                "COPILOT_AUTO_UPDATE": "false",
                "COPILOT_OTEL_ENABLED": "false",
            }
        )
        passed_environment.extend(
            sorted(name for name in child_environment if name.startswith("COPILOT_"))
        )
        secret_names = frozenset({COPILOT_SECRET_ENV})

    if github_access:
        assert github_secret is not None
        child_environment[GITHUB_SECRET_ENV] = github_secret
        passed_environment.append(GITHUB_SECRET_ENV)
        secret_names = secret_names | {GITHUB_SECRET_ENV}

    command = [
        str(launch_cplt_path),
        "--yes",
        "--scratch-dir",
        "--deny-clipboard",
        "--no-quiet",
        "--agent",
        config.client,
        "--project-dir",
        str(project),
        *LOCAL_CPLT_HARDENING_FLAGS,
        "--allow-localhost",
        str(config.port),
        "--allow-read",
        str(payload),
        "--allow-read",
        str(runtime.trusted_bin),
    ]
    if github_executable is not None:
        # cplt's gh wrapper executes the resolved user-owned binary through the
        # trusted-bin symlink. Grant read access to that exact file so a gh
        # installed outside cplt's standard tool roots remains executable.
        command.extend(("--allow-read", str(github_executable)))
    sensitive_paths = list(_existing_host_github_config_dirs(source_environment))
    if config.client == "copilot":
        # The native cplt Copilot profile pre-extracts the signed SEA runtime
        # and grants executable mapping only below its read-only pkg subtree.
        # Do not add a broader user cache-exec carve-out here.
        sensitive_paths.extend(
            _copilot_sensitive_paths(_environment_home(source_environment))
        )
        if config.api_key_file is not None:
            sensitive_paths.append(config.api_key_file)
    for sensitive in dict.fromkeys(sensitive_paths):
        command.extend(("--deny-path", str(sensitive)))
    for writable in (
        runtime.xdg_config,
        runtime.xdg_cache,
        runtime.xdg_data,
        runtime.xdg_state,
        runtime.copilot_home,
    ):
        command.extend(("--allow-write", str(writable)))
    for name in dict.fromkeys(passed_environment):
        command.extend(("--pass-env", name))
    command.append("--")
    command.extend(
        _client_arguments(
            config,
            payload,
            client_arguments,
            run_prompt=run_prompt,
            github_access=github_access,
        )
    )
    return LocalLaunch(
        tuple(command),
        child_environment,
        payload,
        runtime,
        secret_names,
    )


def doctor_local(
    config: LocalConfig,
    *,
    distribution_root: Path,
    project_dir: Path,
    cplt: object,
    client: object,
    github_access: bool = False,
    resolved_github_capability: _ResolvedGithubCapability | None = None,
    environment: Mapping[str, str] | None = None,
    timeout: float = DEFAULT_PROBE_TIMEOUT,
    platform: str | None = None,
) -> tuple[ModelProbe, LocalLaunch]:
    environment = os.environ if environment is None else environment
    config = validate_config(config)
    if github_access and resolved_github_capability is None:
        resolved_github_capability = _explicit_github_capability(environment)
    _validate_launch_trust_roots(
        distribution_root=distribution_root,
        project_dir=project_dir,
        cplt=cplt,
        client=client,
        client_name=config.client,
        environment=environment,
        api_key_file=config.api_key_file,
        github_executable=(
            resolved_github_capability.executable
            if resolved_github_capability is not None
            else None
        ),
    )
    resolved_secret = _ResolvedSecret(_read_secret(config, environment))
    probe = probe_model(
        config,
        environment=environment,
        timeout=timeout,
        resolved_secret=resolved_secret,
    )
    launch = build_local_launch(
        config,
        distribution_root=distribution_root,
        project_dir=project_dir,
        cplt=cplt,
        client=client,
        github_access=github_access,
        environment=environment,
        resolved_secret=resolved_secret,
        resolved_github_capability=resolved_github_capability,
        prepare_state=False,
        platform=platform,
    )
    return probe, launch


def execute_local(
    config: LocalConfig,
    *,
    distribution_root: Path,
    project_dir: Path,
    cplt: object,
    client: object,
    client_arguments: Sequence[str] = (),
    run_prompt: str | None = None,
    github_access: bool = False,
    environment: Mapping[str, str] | None = None,
    timeout: float = DEFAULT_PROBE_TIMEOUT,
    exec_callback: Callable[[str, Sequence[str], Mapping[str, str]], object] = os.execvpe,
    platform: str | None = None,
) -> object:
    """Probe the exact model, then replace the process through native cplt."""

    environment = os.environ if environment is None else environment
    config = validate_config(config)
    if run_prompt is not None:
        if client_arguments:
            raise LocalModeError(
                "local run owns the client command line and accepts only one prompt"
            )
        _validate_run_prompt(run_prompt)
    resolved_github_capability = (
        _explicit_github_capability(environment) if github_access else None
    )
    _validate_launch_trust_roots(
        distribution_root=distribution_root,
        project_dir=project_dir,
        cplt=cplt,
        client=client,
        client_name=config.client,
        environment=environment,
        api_key_file=config.api_key_file,
        github_executable=(
            resolved_github_capability.executable
            if resolved_github_capability is not None
            else None
        ),
    )
    resolved_secret = _ResolvedSecret(_read_secret(config, environment))
    probe_model(
        config,
        environment=environment,
        timeout=timeout,
        resolved_secret=resolved_secret,
    )
    launch = build_local_launch(
        config,
        distribution_root=distribution_root,
        project_dir=project_dir,
        cplt=cplt,
        client=client,
        client_arguments=client_arguments,
        run_prompt=run_prompt,
        github_access=github_access,
        environment=environment,
        resolved_secret=resolved_secret,
        resolved_github_capability=resolved_github_capability,
        platform=platform,
    )
    return exec_callback(launch.command[0], launch.command, launch.environment)


def _discover_clients(environment: Mapping[str, str]) -> tuple[str, ...]:
    """Locate supported clients without executing either ambient binary."""

    path = environment.get("PATH")
    available: list[str] = []
    for client in sorted(CLIENTS):
        resolved = shutil.which(client, path=path)
        if resolved is None:
            continue
        try:
            candidate = Path(resolved).resolve(strict=True)
            observed = candidate.stat()
        except OSError:
            continue
        if stat.S_ISREG(observed.st_mode) and os.access(candidate, os.X_OK):
            available.append(client)
    return tuple(available)


def _interactive_terminal() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


CHOICE_LABELS = {"client": "klient", "model": "modell"}


def _prompt(text: str) -> str:
    try:
        return input(text)
    except (EOFError, KeyboardInterrupt):
        print()
        raise LocalModeError("selection cancelled") from None


def _choose(label: str, values: Sequence[str]) -> str:
    if not values:
        raise LocalModeError(f"no {label} choices are available")
    if len(values) == 1:
        return values[0]
    if not _interactive_terminal():
        raise LocalModeError(
            f"multiple {label} choices are available; select one explicitly"
        )
    prompt_label = CHOICE_LABELS.get(label, label)
    print(f"Velg {prompt_label}:")
    for index, value in enumerate(values, start=1):
        print(f"  {index}. {value}")
    while True:
        answer = _prompt(
            f"{prompt_label.capitalize()} [1-{len(values)}]: "
        ).strip()
        if answer.isdigit() and 1 <= int(answer) <= len(values):
            return values[int(answer) - 1]
        print("Ugyldig valg.")


def _setup_config(
    arguments: argparse.Namespace, environment: Mapping[str, str]
) -> LocalConfig:
    available = _discover_clients(environment)
    client = arguments.client
    if client is None:
        if not available:
            raise LocalModeError(
                "no supported terminal client was found on PATH; install OpenCode "
                f"with '{CLIENT_INSTALL_HINTS['opencode']}' or Copilot CLI with "
                f"'{CLIENT_INSTALL_HINTS['copilot']}'"
            )
        client = _choose("client", available)
    elif client not in available:
        raise LocalModeError(
            f"{client} was not found on PATH; install it with: "
            f"{CLIENT_INSTALL_HINTS[client]}"
        )

    base_url = arguments.base_url
    if base_url is None:
        base_url = DEFAULT_BASE_URL
        if _interactive_terminal():
            entered = _prompt(f"Lokalt endepunkt [{DEFAULT_BASE_URL}]: ").strip()
            if entered:
                base_url = entered

    model_id = arguments.model_id
    provisional = LocalConfig(
        client=client,
        agent=arguments.agent,
        context=arguments.context,
        provider_id=arguments.provider_id,
        base_url=base_url,
        model_id=model_id or "model-discovery",
        context_window=arguments.context_window,
        max_output_tokens=arguments.max_output_tokens,
        api_key_env=arguments.api_key_env,
        api_key_file=arguments.api_key_file,
    )
    provisional = validate_config(provisional)
    models = _advertised_models(provisional, environment=environment)
    if model_id is None:
        model_id = _choose("model", models)
    elif model_id not in models:
        raise LocalModeError(
            f"local endpoint does not advertise exact modelId {model_id!r}"
        )
    return validate_config(replace(provisional, model_id=model_id))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="grillmester local",
        description="Run Grillmester against an explicit local OpenAI-compatible model",
        allow_abbrev=False,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  grillmester local setup\n"
            "  grillmester local\n"
            '  grillmester local run "Fix the failing test"\n'
            "  grillmester local --client copilot\n"
            "  grillmester local --full --agent grillmester\n"
            "  grillmester local doctor\n"
            "  grillmester local --print-command\n\n"
            "The model server and terminal clients are user-installed. Inference is "
            "bound to localhost; network tools remain available through cplt."
        ),
    )
    subparsers = parser.add_subparsers(
        dest="command", required=True, metavar="{setup,status,doctor,launch,run}"
    )
    setup = subparsers.add_parser(
        "setup",
        allow_abbrev=False,
        help="discover a client and verify/save one loopback model",
        description="Verify and save one local client/provider/model default.",
    )
    setup.add_argument(
        "--client",
        choices=sorted(CLIENTS),
        help="installed terminal client (prompted when both are present)",
    )
    setup.add_argument(
        "--agent",
        choices=sorted(PUBLIC_AGENTS),
        default=FOCUSED_AGENT,
        help="default public agent (focused supports only barista)",
    )
    setup_context = setup.add_mutually_exclusive_group()
    setup_context.add_argument(
        "--context",
        choices=sorted(CONTEXTS),
        default="focused",
        help="saved context size (default: focused)",
    )
    setup_context.add_argument(
        "--full",
        action="store_const",
        const="full",
        dest="context",
        help="save full 7-agent/43-skill context",
    )
    setup.add_argument(
        "--provider-id",
        default="local",
        help="OpenAI-compatible provider identifier (default: local)",
    )
    setup.add_argument(
        "--base-url",
        help=f"exact loopback /v1 URL (default: {DEFAULT_BASE_URL})",
    )
    setup.add_argument(
        "--model-id",
        help="exact model advertised by /v1/models (prompted when omitted)",
    )
    setup.add_argument(
        "--context-window",
        type=int,
        default=DEFAULT_CONTEXT_WINDOW,
        help=(
            "safe client context budget in tokens "
            f"(default: {DEFAULT_CONTEXT_WINDOW})"
        ),
    )
    setup.add_argument(
        "--max-output-tokens",
        type=int,
        default=DEFAULT_MAX_OUTPUT_TOKENS,
        help=(
            "maximum tokens reserved for one model response "
            f"(default: {DEFAULT_MAX_OUTPUT_TOKENS})"
        ),
    )
    auth = setup.add_mutually_exclusive_group()
    auth.add_argument(
        "--api-key-env",
        help=(
            "Copilot only: environment variable read only at probe/launch; "
            "OpenCode requires key-free loopback"
        ),
    )
    auth.add_argument(
        "--api-key-file",
        type=Path,
        help=(
            "Copilot only: absolute private key file read at probe/launch; "
            "OpenCode requires key-free loopback"
        ),
    )
    subparsers.add_parser(
        "status",
        allow_abbrev=False,
        help="show the saved connection description without probing",
    )
    doctor = subparsers.add_parser(
        "doctor",
        allow_abbrev=False,
        help="verify cplt, client, endpoint, model and payload without launching",
    )
    doctor.add_argument(
        "--project-dir",
        type=Path,
        default=Path.cwd(),
        help="consumer repository to validate (default: current directory)",
    )
    doctor.add_argument(
        "--client", choices=sorted(CLIENTS), help="one-shot client override"
    )
    doctor.add_argument(
        "--agent", choices=sorted(PUBLIC_AGENTS), help="one-shot agent override"
    )
    doctor.add_argument(
        "--full", action="store_true", help="validate the full context payload"
    )
    doctor.add_argument(
        "--github-access",
        action="store_true",
        help=GITHUB_ACCESS_HELP,
    )
    launch = subparsers.add_parser(
        "launch",
        allow_abbrev=False,
        help="start the saved local model session (default command)",
    )
    launch.add_argument(
        "--project-dir",
        type=Path,
        default=Path.cwd(),
        help="consumer repository for the sandbox (default: current directory)",
    )
    launch.add_argument(
        "--client", choices=sorted(CLIENTS), help="one-shot client override"
    )
    launch.add_argument(
        "--agent", choices=sorted(PUBLIC_AGENTS), help="one-shot agent override"
    )
    launch.add_argument(
        "--full",
        action="store_true",
        help="use the complete agent and skill payload for this launch only",
    )
    launch.add_argument(
        "--print-command",
        action="store_true",
        help=(
            "print a redacted, side-effect-free preview; policy files and secret "
            "environment are not materialized, so it is not a copy/paste command"
        ),
    )
    launch.add_argument(
        "--github-access",
        action="store_true",
        help=GITHUB_ACCESS_HELP,
    )
    launch.add_argument(
        "client_arguments",
        nargs=argparse.REMAINDER,
        help="client arguments after -- (restricted by local mode)",
    )
    run = subparsers.add_parser(
        "run",
        allow_abbrev=False,
        help="run one prompt non-interactively with automatic tool approvals",
        description=(
            "Run one local-model task in foreground, non-interactively through cplt."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "This mode auto-approves project writes and tool commands. Use one run "
            "at a time in a clean, dedicated worktree; cplt does not protect project "
            "files from the model. An exit 0 means client completion, not semantic "
            "task success: inspect the final status, diff and tests."
        ),
    )
    run.add_argument(
        "--project-dir",
        type=Path,
        default=Path.cwd(),
        help="consumer repository for the sandbox (default: current directory)",
    )
    run.add_argument(
        "--client", choices=sorted(CLIENTS), help="one-shot client override"
    )
    run.add_argument(
        "--agent", choices=sorted(PUBLIC_AGENTS), help="one-shot agent override"
    )
    run.add_argument(
        "--full",
        action="store_true",
        help="use the complete agent and skill payload for this task only",
    )
    run.add_argument(
        "--print-command",
        action="store_true",
        help=(
            "print a redacted, side-effect-free preview; policy files and secret "
            "environment are not materialized, so it is not a copy/paste command"
        ),
    )
    run.add_argument(
        "--github-access",
        action="store_true",
        help=(
            "authorize prompt-described GitHub writes without tool prompts using a "
            "dedicated fine-grained GH_TOKEN supplied by the caller; the child can "
            "read it and cplt's gh guard is a soft boundary"
        ),
    )
    run.add_argument("prompt", help="one quoted task prompt")
    return parser


def _status_text(config: LocalConfig) -> str:
    if config.api_key_env is not None:
        authentication = f"environment {config.api_key_env}"
    elif config.api_key_file is not None:
        authentication = f"private file {config.api_key_file}"
    else:
        authentication = "none"
    return "\n".join(
        (
            f"client: {config.client}",
            f"agent: {config.agent}",
            f"context: {config.context}",
            f"provider: {config.provider_id}",
            f"endpoint: {config.base_url}",
            f"model: {config.model_id}",
            f"context window: {config.context_window}",
            f"max output tokens: {config.max_output_tokens}",
            f"authentication: {authentication}",
        )
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    distribution_root: Path | None = None,
    binary_resolver: Callable[[str, bool, Path], tuple[object, object]] | None = None,
    environment: Mapping[str, str] | None = None,
    exec_callback: Callable[[str, Sequence[str], Mapping[str, str]], object] = os.execvpe,
) -> int:
    environment = os.environ if environment is None else environment
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "setup":
            config = _setup_config(arguments, environment)
            destination = save_config(config, environment=environment)
            print(f"Saved local model configuration to {destination}")
            print(
                f"Selected {config.client} with {config.model_id} "
                f"({config.context} {config.agent}); local inference with "
                "connected tools through cplt"
            )
            return 0

        if arguments.command in {"doctor", "launch", "run"}:
            arguments.project_dir = _validate_early_project_trust_roots(
                arguments.project_dir, environment
            )

        try:
            config = load_config(environment=environment)
        except LocalModeError as exc:
            saved_config = config_path(environment)
            if saved_config.is_symlink():
                raise LocalModeError(
                    f"{exc}; remove the symlink {saved_config}, then run "
                    "'grillmester local setup'"
                ) from exc
            raise LocalModeError(
                f"{exc}; run 'grillmester local setup' to create or replace it"
            ) from exc
        if arguments.command == "status":
            print(_status_text(config))
            return 0

        if binary_resolver is None:
            raise LocalModeError(
                "doctor, launch and run must use the top-level 'grillmester local' "
                "launcher so compatible cplt and client versions are verified"
            )

        if arguments.command == "run":
            config = replace(
                config,
                client=arguments.client or config.client,
                agent=arguments.agent or FOCUSED_AGENT,
                context="full" if arguments.full else "focused",
            )
        else:
            config = replace(
                config,
                client=arguments.client or config.client,
                agent=arguments.agent or config.agent,
                context="full" if arguments.full else config.context,
            )
        config = validate_config(config)

        root = (
            Path(__file__).resolve(strict=True).parent.parent
            if distribution_root is None
            else distribution_root
        )
        # The local parser is the sole authority on whether this is a pure
        # preview. Tokens after argparse.REMAINDER must never weaken the
        # cplt/client version gate in the parent launcher.
        checked = (
            arguments.command not in {"launch", "run"}
            or not arguments.print_command
        )
        resolved = binary_resolver(config.client, checked, arguments.project_dir)
        if not isinstance(resolved, tuple) or len(resolved) != 2:
            raise LocalModeError("binary_resolver must return (cplt, client)")
        cplt, client = resolved
        if arguments.command == "doctor":
            github_capability_error: LocalModeError | None = None
            resolved_github_capability: _ResolvedGithubCapability | None = None
            if arguments.github_access:
                try:
                    resolved_github_capability = _explicit_github_capability(
                        environment
                    )
                except LocalModeError as exc:
                    github_capability_error = exc
            probe, launch = doctor_local(
                config,
                distribution_root=root,
                project_dir=arguments.project_dir,
                cplt=cplt,
                client=client,
                github_access=(
                    arguments.github_access and github_capability_error is None
                ),
                resolved_github_capability=resolved_github_capability,
                environment=environment,
            )
            project = arguments.project_dir.expanduser().resolve(strict=True)
            print(f"ok  cplt {_binary_detail(cplt, label='cplt', expected_name='cplt')}")
            print(
                f"ok  client {config.client} "
                f"{_binary_detail(client, label=config.client)}"
            )
            print(f"ok  project {project}")
            print(f"ok  agent {config.agent}")
            print(f"ok  context {config.context}")
            print(f"ok  endpoint {probe.base_url}")
            print(f"ok  model {probe.model_id}")
            print(f"ok  context-window {config.context_window}")
            print(f"ok  max-output-tokens {config.max_output_tokens}")
            print(f"ok  payload {launch.payload}")
            if github_capability_error is not None:
                print(f"error github {github_capability_error}")
            elif arguments.github_access:
                print(
                    "ok  github explicit GH_TOKEN accepted and gh resolved "
                    "(soft boundary; doctor sends no credential)"
                )
            else:
                if config.client == "copilot":
                    print(
                        "warn github env/config credential not exposed; cplt's "
                        "Copilot profile can still access macOS Keychain"
                    )
                else:
                    print(
                        "skip github credential not exposed; use --github-access "
                        "with an explicit GH_TOKEN when needed"
                    )
            if config.client == "opencode":
                print(
                    "info websearch OpenCode sends approved search queries to Exa "
                    "when cplt network policy permits"
                )
                ripgrep = _resolve_ripgrep(environment)
                if ripgrep is None:
                    print(f"warn  {RIPGREP_HINT}")
                else:
                    print(f"ok  rg {ripgrep}")
            if github_capability_error is not None:
                return 1
            return 0

        client_arguments = list(getattr(arguments, "client_arguments", ()))
        if client_arguments[:1] == ["--"]:
            client_arguments.pop(0)
        if arguments.command == "launch" and client_arguments[:1] == ["run"]:
            raise LocalModeError(
                "use one-task mode: place 'run' immediately after "
                "'grillmester local', before --client and other options"
            )
        if arguments.print_command:
            launch = build_local_launch(
                config,
                distribution_root=root,
                project_dir=arguments.project_dir,
                cplt=cplt,
                client=client,
                client_arguments=client_arguments,
                run_prompt=arguments.prompt if arguments.command == "run" else None,
                github_access=arguments.github_access,
                environment=environment,
                resolve_credentials=False,
                prepare_state=False,
            )
            print(shlex.join(launch.command))
            return 0
        execute_local(
            config,
            distribution_root=root,
            project_dir=arguments.project_dir,
            cplt=cplt,
            client=client,
            client_arguments=client_arguments,
            run_prompt=arguments.prompt if arguments.command == "run" else None,
            github_access=arguments.github_access,
            environment=environment,
            exec_callback=exec_callback,
        )
        return 0  # pragma: no cover - os.execvpe does not return
    except LocalModeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
