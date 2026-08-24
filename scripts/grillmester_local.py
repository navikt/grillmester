#!/usr/bin/env python3
"""Configure and launch Grillmester against one explicit local model.

This module deliberately owns neither the model server nor the terminal clients.
It stores only a strict connection description, probes an OpenAI-compatible
loopback endpoint, and constructs a local-only cplt invocation for a caller-
supplied OpenCode or Copilot CLI binary.
"""

from __future__ import annotations

import argparse
import errno
import fcntl
import hashlib
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
import tomllib
import urllib.error
import urllib.request
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable, Mapping, NamedTuple, Sequence
from urllib.parse import urlsplit


CONFIG_SCHEMA_VERSION = 1
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
        "--interactive",
        "--mini",
        "--no-replay",
        "--print-logs",
        "--pure",
        "--thinking",
        "--version",
    }
)
OPENCODE_SAFE_VALUE_OPTIONS = frozenset(
    {
        "--file",
        "--format",
        "--log-level",
        "--replay-limit",
        "--title",
        "--variant",
    }
)
LOCAL_SENTINEL_DOMAIN = "grillmester-local-only.invalid"
COPILOT_SECRET_ENV = "COPILOT_PROVIDER_API_KEY"
MAX_CONFIG_BYTES = 64 * 1024
MAX_SECRET_BYTES = 16 * 1024
MAX_PROBE_BYTES = 256 * 1024
MAX_EXECUTABLE_BYTES = 512 * 1024 * 1024
DEFAULT_PROBE_TIMEOUT = 5.0
DEFAULT_BASE_URL = "http://127.0.0.1:8080/v1"
RETAINED_INACTIVE_SESSIONS = 2
SESSION_OWNER_FILE = "owner.pid"

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
    "OPENCODE_ENABLE_EXA": "false",
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
    """Raised when a local-only configuration or launch is unsafe."""


@dataclass(frozen=True)
class LocalConfig:
    client: str
    agent: str
    context: str
    provider_id: str
    base_url: str
    model_id: str
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


@dataclass(frozen=True)
class RuntimePaths:
    root: Path
    trusted_bin: Path
    home: Path
    xdg_config: Path
    xdg_cache: Path
    xdg_data: Path
    xdg_state: Path
    cplt_config: Path
    allowed_domains: Path
    blocked_domains: Path
    copilot_home: Path


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
    }
    observed_fields = set(raw)
    if observed_fields not in (common, common | {"apiKeyEnv"}, common | {"apiKeyFile"}):
        raise LocalModeError("local config has unexpected or missing fields")
    if raw.get("schemaVersion") != CONFIG_SCHEMA_VERSION:
        raise LocalModeError("local config uses an unsupported schemaVersion")
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
    encoded = value.encode("utf-8")
    if not value or len(encoded) > MAX_SECRET_BYTES:
        raise LocalModeError(f"local API key {label} is empty or too large")
    if "\x00" in value or "\r" in value or "\n" in value:
        raise LocalModeError(f"local API key {label} must be a single text line")
    return value


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        raise LocalModeError("local model probe refused an HTTP redirect")


def _advertised_models(
    config: LocalConfig,
    *,
    environment: Mapping[str, str] | None = None,
    timeout: float = DEFAULT_PROBE_TIMEOUT,
) -> tuple[str, ...]:
    config = validate_config(config)
    if timeout <= 0 or timeout > 60:
        raise LocalModeError("local model probe timeout must be in (0, 60] seconds")
    environment = os.environ if environment is None else environment
    secret = _read_secret(config, environment)
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
) -> ModelProbe:
    models = _advertised_models(
        config, environment=environment, timeout=timeout
    )
    if config.model_id not in models:
        raise LocalModeError(
            f"local endpoint does not advertise exact modelId {config.model_id!r}"
        )
    return ModelProbe(config.base_url, config.model_id, models)


def _runtime_paths(root: Path) -> RuntimePaths:
    home = root / "home"
    xdg = root / "xdg"
    policy = root / "policy"
    cplt = root / "cplt"
    return RuntimePaths(
        root=root,
        trusted_bin=root / "trusted-bin",
        home=home,
        xdg_config=xdg / "config",
        xdg_cache=xdg / "cache",
        xdg_data=xdg / "data",
        xdg_state=xdg / "state",
        cplt_config=cplt / "config.toml",
        allowed_domains=policy / "allowed-domains.txt",
        blocked_domains=policy / "blocked-domains.txt",
        copilot_home=root / "copilot",
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
            trusted_bin = candidate / "trusted-bin"
            try:
                flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
                descriptor = os.open(trusted_bin, flags)
            except FileNotFoundError:
                descriptor = None
            if descriptor is not None:
                try:
                    staged = os.fstat(descriptor)
                    if (
                        not stat.S_ISDIR(staged.st_mode)
                        or (hasattr(os, "geteuid") and staged.st_uid != os.geteuid())
                    ):
                        raise LocalModeError(
                            f"trusted executable staging is not user-owned: {trusted_bin}"
                        )
                    os.fchmod(descriptor, 0o700)
                finally:
                    os.close(descriptor)
            shutil.rmtree(candidate)
        except FileNotFoundError:
            # Concurrent pruning has already achieved the intended state.
            continue
        except OSError as exc:
            raise LocalModeError(
                f"could not remove stale private local session {candidate}: {exc}"
            ) from exc


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
        runtime.trusted_bin,
        runtime.home,
        runtime.xdg_config.parent,
        runtime.xdg_config,
        runtime.xdg_cache,
        runtime.xdg_data,
        runtime.xdg_state,
        runtime.allowed_domains.parent,
        runtime.cplt_config.parent,
        runtime.copilot_home,
    ):
        _ensure_private_directory(directory)
    _atomic_private_write(runtime.cplt_config, b"")
    sentinel = f"{LOCAL_SENTINEL_DOMAIN}\n".encode("ascii")
    _atomic_private_write(runtime.allowed_domains, sentinel)
    _atomic_private_write(runtime.blocked_domains, sentinel)
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


class StagedExecutable(NamedTuple):
    path: Path
    sha256: str


# One roster for the fail-closed cplt sandbox posture. The launch command and
# the parent launcher's version probe must run under the same contract, so
# both consume this constant instead of maintaining their own copies.
LOCAL_CPLT_HARDENING_FLAGS = (
    "--preset",
    "standard",
    "--with-proxy",
    "--proxy-forced",
    "--gh-guard",
    "--git-guard",
    "--no-allow-localhost-any",
    "--no-allow-env-files",
    "--no-allow-tmp-exec",
    "--no-allow-docker",
    "--no-allow-lifecycle-scripts",
)


def _stage_checked_executable(
    value: object,
    *,
    source: Path,
    destination_directory: Path,
    name: str,
    label: str,
) -> StagedExecutable:
    """Copy one checked identity into private state and bind it by digest."""

    expected_digest = getattr(value, "sha256", None)
    if expected_digest is not None and (
        not isinstance(expected_digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", expected_digest) is None
    ):
        raise LocalModeError(f"{label} has an invalid checked sha256 identity")
    destination = destination_directory / name
    digest = hashlib.sha256()
    copied = 0
    try:
        with source.open("rb") as source_file, destination.open("xb") as output:
            observed = os.fstat(source_file.fileno())
            if (
                not stat.S_ISREG(observed.st_mode)
                or observed.st_mode & 0o111 == 0
                or observed.st_size > MAX_EXECUTABLE_BYTES
            ):
                raise LocalModeError(
                    f"{label} must be an executable regular file no larger than "
                    f"{MAX_EXECUTABLE_BYTES} bytes"
                )
            while chunk := source_file.read(1024 * 1024):
                copied += len(chunk)
                if copied > MAX_EXECUTABLE_BYTES:
                    raise LocalModeError(
                        f"{label} grew beyond the executable staging limit"
                    )
                digest.update(chunk)
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        destination.chmod(0o500)
    except BaseException:
        try:
            destination.unlink()
        except FileNotFoundError:
            pass
        raise
    observed_digest = digest.hexdigest()
    if expected_digest is not None and observed_digest != expected_digest:
        destination.unlink()
        raise LocalModeError(
            f"{label} changed after its sandboxed version check; run the command again"
        )
    return StagedExecutable(destination, observed_digest)


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


def _resolve_ripgrep(environment: Mapping[str, str]) -> Path | None:
    search_path = environment.get("PATH")
    if not search_path:
        return None
    found = shutil.which("rg", path=search_path)
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


def _stage_opencode_ripgrep(
    runtime: RuntimePaths, *, environment: Mapping[str, str]
) -> Path | None:
    """Seed the private session cache with the PATH-resolved ripgrep.

    OpenCode 1.18.20 downloads ripgrep on first use, the local egress
    boundary blocks that download, and every session starts from an empty
    private cache. A staged copy keeps Glob/Grep working without opening
    egress; a missing rg degrades only those tools.
    """

    source = _resolve_ripgrep(environment)
    if source is None:
        print(f"warning: {RIPGREP_HINT}", file=sys.stderr)
        return None
    bin_directory = runtime.xdg_cache / "opencode" / "bin"
    bin_directory.parent.mkdir(mode=0o700)
    bin_directory.mkdir(mode=0o700)
    return _stage_checked_executable(
        None,
        source=source,
        destination_directory=bin_directory,
        name="rg",
        label="ripgrep",
    ).path


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


def _read_cplt_toml(path: Path, *, label: str) -> bytes:
    try:
        observed = path.lstat()
    except FileNotFoundError:
        return b""
    except OSError as exc:
        raise LocalModeError(f"could not inspect {label} at {path}: {exc}") from exc
    if stat.S_ISLNK(observed.st_mode) or not stat.S_ISREG(observed.st_mode):
        raise LocalModeError(f"{label} must be a regular, non-symlink file: {path}")
    if observed.st_size > MAX_CONFIG_BYTES:
        raise LocalModeError(f"{label} exceeds the {MAX_CONFIG_BYTES}-byte limit")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise LocalModeError(f"could not read {label} at {path}: {exc}") from exc


def _reject_nonempty_proposals(content: bytes, *, label: str) -> None:
    if not content:
        return
    try:
        value = tomllib.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise LocalModeError(f"{label} is not valid UTF-8 TOML") from exc
    # Pinned cplt drops the complete repository config on a serde or path-safety
    # error. Mirror that exact accepted schema so an intended deny can never
    # disappear silently before local-only starts.
    unknown = sorted(set(value) - {"deny", "propose"})
    if unknown:
        raise LocalModeError(f"{label} has unsupported top-level keys: {unknown}")
    deny = value.get("deny", {})
    if not isinstance(deny, dict):
        raise LocalModeError(f"{label} [deny] must be a table")
    unknown_deny = sorted(set(deny) - {"env", "paths"})
    if unknown_deny:
        raise LocalModeError(f"{label} [deny] has unsupported keys: {unknown_deny}")
    denied_environment = deny.get("env", [])
    if not isinstance(denied_environment, list) or any(
        not isinstance(name, str)
        or not name
        or any(
            not (
                character.isascii()
                and (character.isalnum() or character == "_")
            )
            for character in name
        )
        for name in denied_environment
    ):
        raise LocalModeError(
            f"{label} deny.env must contain [A-Za-z0-9_] identifiers"
        )
    denied_paths = deny.get("paths", [])
    unsafe = {'"', ")", "(", ";", "\\", "\n", "\r", "\0"}
    if not isinstance(denied_paths, list) or any(
        not isinstance(path, str)
        or ".." in Path(path).parts
        or any(character in path for character in unsafe)
        for path in denied_paths
    ):
        raise LocalModeError(
            f"{label} deny.paths contains traversal or unsafe characters"
        )
    proposed = value.get("propose", {})
    if not isinstance(proposed, dict):
        raise LocalModeError(f"{label} [propose] must be a table")
    if proposed:
        raise LocalModeError(
            f"local-only mode refuses non-empty [propose] permissions in {label}"
        )


def _trusted_git_binary() -> Path:
    for candidate in (Path("/usr/bin/git"), Path("/opt/homebrew/bin/git"), Path("/usr/local/bin/git")):
        try:
            observed = candidate.stat()
        except OSError:
            continue
        if stat.S_ISREG(observed.st_mode) and os.access(candidate, os.X_OK):
            return candidate
    raise LocalModeError("could not inspect committed .cplt.toml without a trusted git binary")


def _git_command(git: Path, root: Path, arguments: Sequence[str]) -> subprocess.CompletedProcess[bytes]:
    environment = {
        "PATH": "/usr/bin:/bin",
        "HOME": "/nonexistent-grillmester-local-git-home",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
        "LC_ALL": "C",
    }
    try:
        return subprocess.run(
            [str(git), "-C", str(root), *arguments],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LocalModeError(f"could not inspect committed .cplt.toml: {exc}") from exc


def _committed_cplt_toml(root: Path) -> bytes:
    git = _trusted_git_binary()
    head_result = _git_command(git, root, ("rev-parse", "--verify", "-q", "HEAD"))
    if head_result.returncode != 0:
        return b""
    head = head_result.stdout.decode("ascii", errors="strict").strip()
    if not re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", head):
        raise LocalModeError("repository HEAD did not resolve to one exact object ID")
    object_name = f"{head}:.cplt.toml"
    listing = _git_command(git, root, ("ls-tree", "--name-only", head, "--", ".cplt.toml"))
    if listing.returncode != 0:
        raise LocalModeError("could not inspect committed .cplt.toml tree entry")
    if listing.stdout == b"":
        return b""
    if listing.stdout != b".cplt.toml\n":
        raise LocalModeError("committed .cplt.toml has an unexpected tree identity")
    size_result = _git_command(git, root, ("cat-file", "-s", object_name))
    try:
        size = int(size_result.stdout.decode("ascii").strip())
    except (UnicodeDecodeError, ValueError) as exc:
        raise LocalModeError("could not determine committed .cplt.toml size") from exc
    if size_result.returncode != 0 or size < 0 or size > MAX_CONFIG_BYTES:
        raise LocalModeError(
            f"committed .cplt.toml exceeds the {MAX_CONFIG_BYTES}-byte limit"
        )
    content = _git_command(git, root, ("show", "--no-ext-diff", "--no-textconv", object_name))
    if content.returncode != 0 or len(content.stdout) != size:
        raise LocalModeError("could not read the exact committed .cplt.toml object")
    return content.stdout


def reject_repository_cplt_proposals(project: Path) -> Path:
    """Fail closed on every repo permission proposal local-only could inherit."""

    root, is_git = _physical_repository_root(project)
    worktree = _read_cplt_toml(root / ".cplt.toml", label="worktree .cplt.toml")
    _reject_nonempty_proposals(worktree, label="worktree .cplt.toml")
    if is_git:
        committed = _committed_cplt_toml(root)
        _reject_nonempty_proposals(committed, label="committed .cplt.toml")
    return root


def reject_project_opencode_extensions(project: Path) -> None:
    """Reject OpenCode's project-level executable/config discovery surface."""

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
                f"local-only mode refuses auto-discovered project OpenCode config: {candidate}"
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
        try:
            entries = sorted(extension_root.iterdir(), key=lambda entry: entry.name)
        except OSError as exc:
            raise LocalModeError(
                f"could not enumerate project OpenCode directory {extension_root}: {exc}"
            ) from exc
        if entries:
            raise LocalModeError(
                "local-only mode refuses auto-discovered project OpenCode entry: "
                f"{entries[0]}"
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
            f"local-only mode refuses auto-discovered project {client} {component}: "
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
                "local-only mode refuses auto-discovered project Copilot executable config: "
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
                    "local-only mode refuses auto-discovered project Copilot extension: "
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
                    "local-only mode refuses auto-discovered project Copilot hook: "
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
    # The canonical Copilot plugin has no target manifest; it is verified by
    # its plugin.json identity instead.
    ("copilot", "full"): (Path("plugin"), None),
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
    if expected_target is not None:
        _verify_manifested_payload(candidate, expected_target=expected_target)
    else:
        manifest = _read_json_file(candidate / "plugin.json", label="Copilot plugin manifest")
        if manifest.get("name") != "grillmester":
            raise LocalModeError("Copilot plugin payload does not name grillmester")
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
                    }
                },
            }
        },
    }
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _copilot_settings() -> bytes:
    value = {
        "autoUpdate": False,
        "customAgents": {"defaultLocalOnly": True},
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
    result = {
        name: source[name]
        for name in SAFE_HOST_ENVIRONMENT
        if name in source and "\x00" not in source[name]
    }
    path_entries: list[str] = []
    for entry in (client_search_directory, cplt.parent, Path("/usr/bin"), Path("/bin"), Path("/usr/sbin"), Path("/sbin")):
        rendered = str(entry)
        if rendered not in path_entries:
            path_entries.append(rendered)
    result.update(
        {
            "PATH": os.pathsep.join(path_entries),
            "HOME": str(runtime.home),
            "XDG_CONFIG_HOME": str(runtime.xdg_config),
            "XDG_CACHE_HOME": str(runtime.xdg_cache),
            "XDG_DATA_HOME": str(runtime.xdg_data),
            "XDG_STATE_HOME": str(runtime.xdg_state),
            "CPLT_CONFIG": str(runtime.cplt_config),
            "NO_PROXY": "127.0.0.1,localhost,::1",
            "no_proxy": "127.0.0.1,localhost,::1",
        }
    )
    return result


def _copilot_sensitive_paths(home: Path) -> tuple[Path, ...]:
    candidates = (
        home / ".copilot",
        home / ".agents",
        home / ".claude",
        home / ".config" / "gh",
        home / ".config" / "github-copilot",
        home / "Library" / "Keychains",
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
        boolean_options = frozenset({"h", "i", "v"})
        value_options = frozenset({"f"})
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
    """Allow only the reviewed OpenCode 1.18.20 TUI/run option surface."""

    run_mode = bool(arguments) and arguments[0] == "run"
    index = 1 if run_mode else 0
    short_value_options = frozenset({"f"})
    while index < len(arguments):
        argument = arguments[index]
        if argument == "--":
            if run_mode:
                # Everything after -- is the reviewed run message.
                return
            raise LocalModeError(
                "local-only OpenCode accepts the TUI, 'run', --help, or "
                "--version; use the system OpenCode command directly for "
                "other modes"
            )
        if not argument.startswith("-") or argument == "-":
            if run_mode:
                index += 1
                continue
            # Outside run, a positional would select an OpenCode command or
            # an unscanned project directory.
            raise LocalModeError(
                "local-only OpenCode accepts the TUI, 'run', --help, or "
                "--version; use the system OpenCode command directly for "
                "other modes"
            )
        if not argument.startswith("--"):
            # Exact short options and clusters were fully classified above.
            # A trailing value-taking member consumes the next token, so that
            # token stays data instead of counting as a positional.
            cluster = argument[1:]
            for position, member in enumerate(cluster):
                if member in short_value_options:
                    if position == len(cluster) - 1:
                        index += 1
                    break
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
    """Keep local-only Copilot in a fresh TUI or prompt session.

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
                    "local-only Copilot does not accept command-mode positional arguments; "
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
            "local-only Copilot does not accept command-mode positional arguments; "
            "run the system copilot command directly for admin commands"
        )


def _client_arguments(config: LocalConfig, payload: Path, arguments: Sequence[str]) -> list[str]:
    _validate_client_arguments(config.client, arguments)
    if config.client == "opencode":
        binding = ["--agent", config.agent, "--model", config.qualified_model]
        if not arguments:
            return binding
        if arguments and arguments[0] == "run":
            return ["run", *binding, *arguments[1:]]
        if tuple(arguments) in OPENCODE_SAFE_META_ARGUMENTS:
            return list(arguments)
        if arguments[0].startswith("-"):
            return [*binding, *arguments]
        raise LocalModeError(
            "local-only OpenCode accepts the TUI, 'run', --help, or --version; "
            "use the system OpenCode command directly for admin commands or another project"
        )
    return [
        "--plugin-dir",
        str(payload),
        "--agent",
        f"grillmester:{config.agent}",
        "--model",
        config.model_id,
        "--effort",
        "low",
        "--no-auto-update",
        "--no-experimental",
        "--no-remote",
        "--no-remote-export",
        "--disable-builtin-mcps",
        f"--secret-env-vars={COPILOT_SECRET_ENV}",
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
    environment: Mapping[str, str] | None = None,
    resolve_credentials: bool = True,
    prepare_state: bool = True,
    platform: str | None = None,
) -> LocalLaunch:
    """Build one local-only command without executing cplt or either client."""

    platform = sys.platform if platform is None else platform
    if platform != "darwin":
        raise LocalModeError(
            "local-only launch is currently supported only on macOS, where the "
            "tested cplt baseline enforces forced-proxy egress"
        )
    config = validate_config(config, check_key_file=resolve_credentials)
    source_environment = os.environ if environment is None else environment
    cplt_path = _binary_path(cplt, label="cplt", expected_name="cplt")
    client_path = _binary_path(client, label=config.client)
    try:
        project = project_dir.expanduser().resolve(strict=True)
        project_observed = project.stat()
    except OSError as exc:
        raise LocalModeError(f"could not resolve local project directory: {exc}") from exc
    if not stat.S_ISDIR(project_observed.st_mode):
        raise LocalModeError("local project path must be a directory")
    if (
        resolve_credentials
        and config.api_key_file is not None
        and _existing_path_is_within(config.api_key_file, project)
    ):
        raise LocalModeError(
            "apiKeyFile must be outside the consumer project so the sandboxed "
            "client can never read the original credential file"
        )
    reject_repository_cplt_proposals(project)
    if config.client == "opencode":
        reject_project_opencode_extensions(project)
    else:
        reject_project_copilot_hooks(project)
    payload = _payload_path(distribution_root, config)
    secret_configured = config.api_key_env is not None or config.api_key_file is not None
    secret = _read_secret(config, source_environment) if resolve_credentials else None
    runtime = (
        _prepare_runtime(source_environment, config.client)
        if prepare_state
        else _planned_runtime(source_environment, config.client)
    )
    if prepare_state:
        launch_cplt_path = _stage_checked_executable(
            cplt,
            source=cplt_path,
            destination_directory=runtime.trusted_bin,
            name="cplt",
            label="cplt",
        ).path
        _stage_checked_executable(
            client,
            source=client_path,
            destination_directory=runtime.trusted_bin,
            name=config.client,
            label=config.client,
        )
        if config.client == "opencode":
            _stage_opencode_ripgrep(runtime, environment=source_environment)
        runtime.trusted_bin.chmod(0o500)
        client_search_directory = runtime.trusted_bin
    else:
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
        passed_environment.extend(
            ["OPENCODE_CONFIG_DIR", "OPENCODE_CONFIG_CONTENT", *sorted(OPENCODE_LOCAL_ENVIRONMENT)]
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
                "COPILOT_PROVIDER_MAX_PROMPT_TOKENS": "28672",
                "COPILOT_PROVIDER_MAX_OUTPUT_TOKENS": "4096",
                "COPILOT_MODEL": config.model_id,
                "COPILOT_OFFLINE": "true",
                "COPILOT_AUTO_UPDATE": "false",
                "COPILOT_OTEL_ENABLED": "false",
            }
        )
        passed_environment.extend(
            sorted(name for name in child_environment if name.startswith("COPILOT_"))
        )
        secret_names = frozenset({COPILOT_SECRET_ENV})

    command = [
        str(launch_cplt_path),
        "--yes",
        "--scratch-dir",
        "--deny-clipboard",
        # cplt's parent-side post-session Git audit can execute a consumer
        # core.fsmonitor command outside the sandbox. Normal Grillmester keeps
        # the audit; local-only disables it to preserve the host boundary.
        "--no-audit",
        "--no-quiet",
        "--agent",
        config.client,
        "--project-dir",
        str(project),
        *LOCAL_CPLT_HARDENING_FLAGS,
        "--allowed-domains",
        str(runtime.allowed_domains),
        "--blocked-domains",
        str(runtime.blocked_domains),
        "--allow-localhost",
        str(config.port),
        "--allow-read",
        str(payload),
    ]
    if config.client == "copilot":
        # Copilot extracts its signed runtime and native addon below its isolated
        # HOME cache. cplt blocks mmap/exec from caches unless this exact private
        # subdirectory is named explicitly.
        command.extend(("--allow-cache-exec", "copilot"))
        sensitive_paths = list(
            _copilot_sensitive_paths(_environment_home(source_environment))
        )
        if config.api_key_file is not None:
            sensitive_paths.append(config.api_key_file)
        for sensitive in dict.fromkeys(sensitive_paths):
            command.extend(("--deny-path", str(sensitive)))
    for writable in (
        runtime.home,
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
    command.extend(_client_arguments(config, payload, client_arguments))
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
    environment: Mapping[str, str] | None = None,
    timeout: float = DEFAULT_PROBE_TIMEOUT,
    platform: str | None = None,
) -> tuple[ModelProbe, LocalLaunch]:
    environment = os.environ if environment is None else environment
    probe = probe_model(config, environment=environment, timeout=timeout)
    launch = build_local_launch(
        config,
        distribution_root=distribution_root,
        project_dir=project_dir,
        cplt=cplt,
        client=client,
        environment=environment,
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
    environment: Mapping[str, str] | None = None,
    timeout: float = DEFAULT_PROBE_TIMEOUT,
    exec_callback: Callable[[str, Sequence[str], Mapping[str, str]], object] = os.execvpe,
    platform: str | None = None,
) -> object:
    """Probe the exact model, then replace the process through native cplt."""

    environment = os.environ if environment is None else environment
    probe_model(config, environment=environment, timeout=timeout)
    launch = build_local_launch(
        config,
        distribution_root=distribution_root,
        project_dir=project_dir,
        cplt=cplt,
        client=client,
        client_arguments=client_arguments,
        environment=environment,
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
            "  grillmester local --client copilot\n"
            "  grillmester local --full --agent grillmester\n"
            "  grillmester local doctor\n"
            "  grillmester local --print-command\n\n"
            "The model server and terminal clients are user-installed. Every launch "
            "uses exact reviewed cplt with no cloud fallback."
        ),
    )
    subparsers = parser.add_subparsers(
        dest="command", required=True, metavar="{setup,status,doctor,launch}"
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
        help="save full 7-agent/42-skill context",
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
    auth = setup.add_mutually_exclusive_group()
    auth.add_argument(
        "--api-key-env", help="name of an environment variable read only at probe/launch"
    )
    auth.add_argument(
        "--api-key-file", type=Path, help="absolute private key file read at probe/launch"
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
        "client_arguments",
        nargs=argparse.REMAINDER,
        help="client arguments after -- (restricted by local-only mode)",
    )
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
            f"authentication: {authentication}",
        )
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    distribution_root: Path | None = None,
    binary_resolver: Callable[[str, bool], tuple[object, object]] | None = None,
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
                f"({config.context} {config.agent})"
            )
            return 0

        try:
            config = load_config(environment=environment)
        except LocalModeError as exc:
            raise LocalModeError(
                f"{exc}; run 'grillmester local setup' to create or replace it"
            ) from exc
        if arguments.command == "status":
            print(_status_text(config))
            return 0

        if binary_resolver is None:
            raise LocalModeError(
                "doctor and launch must run through the top-level 'grillmester local' "
                "launcher so exact reviewed cplt and client binaries are verified"
            )

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
        checked = arguments.command != "launch" or not arguments.print_command
        resolved = binary_resolver(config.client, checked)
        if not isinstance(resolved, tuple) or len(resolved) != 2:
            raise LocalModeError("binary_resolver must return (cplt, client)")
        cplt, client = resolved
        if arguments.command == "doctor":
            probe, launch = doctor_local(
                config,
                distribution_root=root,
                project_dir=arguments.project_dir,
                cplt=cplt,
                client=client,
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
            print(f"ok  payload {launch.payload}")
            if config.client == "opencode":
                ripgrep = _resolve_ripgrep(environment)
                if ripgrep is None:
                    print(f"warn  {RIPGREP_HINT}")
                else:
                    print(f"ok  rg {ripgrep}")
            return 0

        client_arguments = list(arguments.client_arguments)
        if client_arguments[:1] == ["--"]:
            client_arguments.pop(0)
        if arguments.print_command:
            launch = build_local_launch(
                config,
                distribution_root=root,
                project_dir=arguments.project_dir,
                cplt=cplt,
                client=client,
                client_arguments=client_arguments,
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
            environment=environment,
            exec_callback=exec_callback,
        )
        return 0  # pragma: no cover - os.execvpe does not return
    except LocalModeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
