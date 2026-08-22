#!/usr/bin/env python3
"""Install and launch Grillmester's generated OpenCode target safely.

The generated target is immutable input. Installations are content-addressed,
manifest-verified releases in user-owned data, while every OpenCode process gets
its own read-only config staging directory under lifecycle-owned data. No consumer
repository is used as an install or staging target.
"""

from __future__ import annotations

import argparse
import copy
import errno
import fcntl
import hashlib
import ipaddress
import json
import os
import platform
import pwd
import re
import selectors
import signal
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import tomllib
import types
import unicodedata
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Iterator, Mapping, Sequence
from urllib.parse import urlsplit


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = REPOSITORY_ROOT
PROFILE_ROOT = REPOSITORY_ROOT / "profiles/opencode"
TARGET_NAME = "opencode-v1"
TARGET_RELATIVE = PurePosixPath("targets/opencode-v1")
PROFILE_RELATIVE = PurePosixPath("profiles/opencode")
MANAGER_RELATIVE = PurePosixPath("scripts/manage_opencode.py")
PERMISSION_COMPOSER_RELATIVE = PurePosixPath(
    "scripts/compose_opencode_permissions.py"
)
ARTIFACT_VERIFIER_RELATIVE = PurePosixPath("scripts/verify_client_artifact.py")
CLIENT_ARTIFACTS_RELATIVE = PurePosixPath("policy/client-artifacts.json")
CONTENT_LOCK_RELATIVE = PurePosixPath("policy/content-lock.json")
LICENSE_RELATIVE = PurePosixPath("LICENSE")
PROVENANCE_RELATIVE = PurePosixPath("PROVENANCE.md")
THIRD_PARTY_NOTICES_RELATIVE = PurePosixPath("THIRD_PARTY_NOTICES.md")
DISTRIBUTION_MANIFEST = "DISTRIBUTION-MANIFEST.json"
SUPPORTED_OPENCODE_VERSION = "1.18.20"
SUPPORTED_CPLT_RELEASE = "2026.08.17-062831-1008a92"
OPENCODE_OVERLAY_SKILL_IDS = frozenset(
    {"grillmester-create-a-skill", "grillmester-doctor"}
)
PERMISSION_COMPOSER_SHA256 = (
    "e5ff43aeb6b301c46d809068b66977fa35fdd35b251392ce8e03383e72085b26"
)
# SHA-256 of the extracted `cplt` executable in each upstream release asset.
# The archive checksums are published by cplt; these executable digests were
# derived from those checksum-verified, single-file archives and are reviewable
# as part of the immutable lifecycle manager.
PINNED_CPLT_BINARY_SHA256 = {
    ("darwin", "arm64"): "423af2ce6166b0ddc1939d2e4d1340837daa23a29ccc58024ec0a849051becb2",
    ("darwin", "x86_64"): "36592c1b2bcfd7ab2d9083842b0aa7f51737cdf12ec1752d351bd9467dab5c02",
    ("linux", "aarch64"): "56715bc8c63d4dd7323d17a48d3c8d64fdfa3450848651a9ac360f6124d12789",
    ("linux", "x86_64"): "115fff00248f0c170388e11f2a05cc9914f5ba589f2ca87817ed96de2c6eedb5",
}
# SHA-256 of the executable bytes in the registry-integrity-verified OpenCode
# 1.18.20 platform packages.  Linux accepts either official libc variant for
# the current CPU architecture; Darwin packages have one executable variant.
PINNED_OPENCODE_BINARY_SHA256 = {
    ("darwin", "arm64", "default"): "9598c27bda0e2d88ce4db5f853e25504c20ac6152e10205785a1cf8f45559952",
    ("darwin", "x86_64", "default"): "96e4a9ecd931a059515fb2126cf59a4a3b56d9a66f9d4dbdf1361d1b4cd5ef60",
    ("linux", "aarch64", "glibc"): "cc9923aa75f8817261326e81fc56f9cb8203d282c0fab9bff7845cae9f6fe740",
    ("linux", "aarch64", "musl"): "556ca2125cba1c1508052d055ee87ada1f28dde8a501986edbdbdf476083e4a6",
    ("linux", "x86_64", "glibc"): "5dce99ea079d925736e332b20f5bf869fe9a1fa67dc0a09027156b0ed8e41b16",
    ("linux", "x86_64", "musl"): "ca872f52047dd9e56b0a7a14da5cda064c3249a4a1116e71b31cab11864a3967",
}
LOCAL_ONLY_ALLOWED_DOMAIN = "grillmester-local-only.invalid"
LOCAL_ONLY_BLOCKED_DOMAINS = frozenset(
    {
        "registry.npmjs.org",
        "registry.yarnpkg.com",
        "repo.maven.apache.org",
        "plugins.gradle.org",
        "crates.io",
        "static.crates.io",
        "pypi.org",
        "files.pythonhosted.org",
        "opencode.ai",
        "models.dev",
    }
)
OPENCODE_RUNTIME_GITIGNORE = (
    b"node_modules\npackage.json\npackage-lock.json\nbun.lock\n.gitignore\n"
)
OPENCODE_RUNTIME_GITIGNORE_PATH = PurePosixPath(".gitignore")
# OpenCode 1.18.20/Bun can lose the tail of a single asynchronous stdout write
# when stdout is a pipe and the process exits immediately. The observed flush
# boundary is 64 KiB; keep resolved config/agent probes comfortably below it.
PINNED_BUN_PIPE_FLUSH_BOUNDARY = 65_536
PINNED_BUN_PIPE_SAFE_OUTPUT_BUDGET = 49_152
OPENCODE_CONFIG_PROBE_MARKER = "Managed OpenCode config probe"
OPENCODE_SKILL_PROBE_MARKER = "Managed OpenCode skill probe"
STATE_SCHEMA_VERSION = 1
PROFILE_SCHEMA_VERSION = 1
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_JSON_DEPTH = 40
MAX_FILE_BYTES = 5_000_000
MAX_EXECUTABLE_BYTES = 256 * 1024 * 1024
MAX_PREFLIGHT_OUTPUT_BYTES = 2 * 1024 * 1024
PREFLIGHT_TIMEOUT_SECONDS = 60
SAFE_PROVIDER_NPM = "@ai-sdk/openai-compatible"
MAX_DISTRIBUTION_BYTES = 50_000_000
MAX_DISTRIBUTION_MEMBERS = 10_000
RELEASE_ID_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SOURCE_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
ENVIRONMENT_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
DOMAIN_LABEL_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
SAFE_STATE_MODE = 0o600
ALLOWED_BUNDLE_MODES = frozenset({0o644, 0o755})
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
MANAGED_AGENT_IDS = frozenset(
    {
        "barista",
        "designer",
        "doctor-who",
        "grill-inspektor",
        "grillmester",
        "kokk",
        "researcher",
    }
)
BASE_PROFILE_ENVIRONMENT = {
    "OPENCODE_CONFIG_CONTENT": '{"autoupdate":false,"share":"disabled"}',
    "OPENCODE_DISABLE_AUTOUPDATE": "true",
    "OPENCODE_DISABLE_CLAUDE_CODE_SKILLS": "true",
    "OPENCODE_DISABLE_CLAUDE_CODE_PROMPT": "true",
    "OPENCODE_DISABLE_DEFAULT_PLUGINS": "true",
    "OPENCODE_DISABLE_EXTERNAL_SKILLS": "true",
    "OPENCODE_DISABLE_SHARE": "true",
    "OPENCODE_DISABLE_MODELS_FETCH": "true",
    "OPENCODE_DISABLE_LSP_DOWNLOAD": "true",
    "OPENCODE_DISABLE_PROJECT_CONFIG": "true",
    "OPENCODE_DB": ":memory:",
    "OPENCODE_EXPERIMENTAL_DISABLE_FILEWATCHER": "true",
    "OPENCODE_EXPERIMENTAL": "false",
    "OPENCODE_EXPERIMENTAL_CODE_MODE": "false",
    # OpenCode otherwise discovers and imports executable consumer/user plugins
    # before its tool permission policy can protect the repository.
    # The Effect runtime accepts the canonical boolean string. OpenCode 1.18.20's
    # CLI --pure handler rewrites this to "1", which its server-side flag parser
    # does not reliably interpret as true, so managed callers cannot pass that flag.
    "OPENCODE_PURE": "true",
}
MANAGER_DYNAMIC_ENVIRONMENT = frozenset(
    {
        "OPENCODE_AUTH_CONTENT",
        "OPENCODE_TEST_HOME",
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_STATE_HOME",
    }
)
LOCAL_ONLY_ENVIRONMENT = {
    **BASE_PROFILE_ENVIRONMENT,
    "OPENCODE_DISABLE_MODELS_FETCH": "true",
    "OPENCODE_DISABLE_LSP_DOWNLOAD": "true",
    "OPENCODE_AUTO_SHARE": "false",
    "OPENCODE_ENABLE_EXA": "false",
}
PROFILE_SHAPES = {
    "local": ("strict", "required", "forbidden"),
    "cloud-open-weight": ("strict", "forbidden", "required"),
    "hybrid": ("strict", "required", "required"),
    "local-only": ("local-only", "required", "forbidden"),
}
CONTROL_ENVIRONMENT_NAMES = frozenset(
    {
        "CPLT_CONFIG",
        "HOME",
        "PATH",
        "PWD",
        "SHELL",
        "TMPDIR",
        "TEMP",
        "TMP",
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_RUNTIME_DIR",
        "XDG_STATE_HOME",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
        "OPENCODE_CONFIG_DIR",
    }
)
SAFE_CPLT_HOST_ENVIRONMENT = frozenset(
    {
        "COLORTERM",
        "HOME",
        "LANG",
        "LC_ALL",
        "LOGNAME",
        "PATH",
        "SYSTEMROOT",
        "TERM",
        "TERM_PROGRAM",
        "USER",
        "WINDIR",
        "CPLT_CONFIG",
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_RUNTIME_DIR",
        "XDG_STATE_HOME",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "CURL_CA_BUNDLE",
        "NODE_EXTRA_CA_CERTS",
    }
)
FORBIDDEN_LOADER_ENVIRONMENT = frozenset(
    {
        "BASH_ENV",
        "DOTNET_STARTUP_HOOKS",
        "ENV",
        "GCONV_PATH",
        "GRADLE_OPTS",
        "JAVA_TOOL_OPTIONS",
        "JDK_JAVA_OPTIONS",
        "LD_PRELOAD",
        "LD_AUDIT",
        "LD_LIBRARY_PATH",
        "LUA_INIT",
        "MAVEN_OPTS",
        "NODE_OPTIONS",
        "BUN_OPTIONS",
        "OPENSSL_CONF",
        "OPENSSL_ENGINES",
        "OPENSSL_MODULES",
        "PERL5OPT",
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONSTARTUP",
        "PYTHONINSPECT",
        "RUBYOPT",
        "ZDOTDIR",
        "_JAVA_OPTIONS",
    }
)
FORBIDDEN_CPLT_HARDENING_ENVIRONMENT = frozenset(
    {
        "DISABLE_AUTOUPDATER",
        "GIT_CONFIG_COUNT",
        "GIT_CONFIG_NOSYSTEM",
        "GIT_DIR",
        "GIT_TERMINAL_PROMPT",
        "GIT_WORK_TREE",
        "NPM_CONFIG_IGNORE_SCRIPTS",
        "YARN_ENABLE_SCRIPTS",
    }
)
CPLT_WRITABLE_TOOL_ENVIRONMENT = frozenset(
    {
        "GOPATH",
        "GOMODCACHE",
        "GOCACHE",
        "CARGO_HOME",
        "NPM_CONFIG_CACHE",
        "npm_config_cache",
        "YARN_CACHE_FOLDER",
        "PNPM_HOME",
        "PIP_CACHE_DIR",
    }
)
SAFE_CPLT_TOOL_ENVIRONMENT = frozenset(
    {
        *CPLT_WRITABLE_TOOL_ENVIRONMENT,
        "JAVA_HOME",
        "NODE_PATH",
    }
)
LIST_TOOL_ENVIRONMENT = frozenset({"GOPATH", "NODE_PATH"})
DEFAULT_ONLY_CPLT_TOOL_ENVIRONMENT = {
    "GRADLE_USER_HOME": ".gradle",
    "RUSTUP_HOME": ".rustup",
    "ASDF_DIR": ".asdf",
    "ASDF_DATA_DIR": ".asdf",
    "NVM_DIR": ".nvm",
    # Pinned cplt has no relocatable grant for these installation roots. They
    # are accepted only when a consumer deliberately keeps them in its already
    # writable project tree.
    "GRADLE_HOME": None,
    "MAVEN_HOME": None,
}


class LifecycleError(RuntimeError):
    """Raised when lifecycle work cannot continue without weakening safety."""


@dataclass(frozen=True)
class ManifestEntry:
    relative: PurePosixPath
    sha256: str
    mode: int


@dataclass(frozen=True)
class VerifiedBundle:
    root: Path
    manifest_bytes: bytes
    release_id: str
    entries: tuple[ManifestEntry, ...]


@dataclass(frozen=True)
class VerifiedDistribution:
    root: Path
    manifest_bytes: bytes
    release_id: str
    entries: tuple[ManifestEntry, ...]
    target: VerifiedBundle


@dataclass(frozen=True)
class RuntimeProfile:
    id: str
    description: str
    cplt_policy: str
    local_ports: str
    provider_domains: str
    environment: Mapping[str, str]
    cplt_release: str | None = None
    allowed_domain: str | None = None
    blocked_domains: tuple[str, ...] = ()


@dataclass(frozen=True)
class RuntimeInputs:
    profile: RuntimeProfile
    local_ports: tuple[int, ...]
    provider_domains: tuple[str, ...]
    provider_ports: tuple[int, ...]
    private_provider_domains: tuple[str, ...]
    pass_environment: tuple[str, ...]
    auth_providers: tuple[str, ...]
    provider_ids: tuple[str, ...]
    provider_base_urls: tuple[tuple[str, str], ...]
    provider_models: tuple[tuple[str, str], ...]


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LifecycleError("duplicate JSON key")
        result[key] = value
    return result


def _reject_nonstandard_json_constant(value: str) -> None:
    raise LifecycleError(f"non-standard JSON constant is forbidden: {value}")


def _require_bounded_json_depth(value: object, *, label: str) -> None:
    pending = [(value, 0)]
    while pending:
        current, depth = pending.pop()
        if depth > MAX_JSON_DEPTH:
            raise LifecycleError(f"{label} is too deeply nested")
        if isinstance(current, Mapping):
            pending.extend((child, depth + 1) for child in current.values())
        elif isinstance(current, list):
            pending.extend((child, depth + 1) for child in current)


def _parse_json_object(content: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_nonstandard_json_constant,
        )
    except UnicodeDecodeError as exc:
        raise LifecycleError(f"{label} is not UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise LifecycleError(
            f"{label} is not valid JSON at line {exc.lineno}, column {exc.colno}"
        ) from exc
    except RecursionError as exc:
        raise LifecycleError(f"{label} is too deeply nested") from exc
    if not isinstance(value, dict):
        raise LifecycleError(f"{label} must be a JSON object")
    _require_bounded_json_depth(value, label=label)
    return value


def _account_home() -> Path:
    """Return the OS account home without trusting a caller-controlled HOME."""

    try:
        return Path(pwd.getpwuid(os.geteuid()).pw_dir)
    except (KeyError, OSError) as exc:  # pragma: no cover - broken account database
        raise LifecycleError(f"could not resolve the current account home: {exc}") from exc


def audited_cplt_home() -> Path:
    return _account_home() / ".local/share/grillmester/opencode"


def default_home(environment: Mapping[str, str] = os.environ) -> Path:
    configured = environment.get("GRILLMESTER_OPENCODE_HOME")
    if configured:
        return Path(configured).expanduser()
    return audited_cplt_home()


def default_runtime_root(
    home: Path, environment: Mapping[str, str] = os.environ
) -> Path:
    configured = environment.get("GRILLMESTER_OPENCODE_RUNTIME_ROOT")
    if configured:
        return Path(configured).expanduser()
    return home / "runtime"


def _resolved(path: Path) -> Path:
    try:
        return path.expanduser().absolute().resolve(strict=False)
    except OSError as exc:
        raise LifecycleError(f"could not resolve lifecycle path {path}: {exc}") from exc


def _portable_absolute_path_key(path: Path) -> tuple[str, ...]:
    """Match path aliases on case-insensitive, Unicode-normalizing filesystems."""

    return tuple(
        unicodedata.normalize("NFC", part).casefold() for part in path.parts
    )


def _is_within(path: Path, parent: Path) -> bool:
    path_key = _portable_absolute_path_key(path)
    parent_key = _portable_absolute_path_key(parent)
    return (
        len(path_key) >= len(parent_key)
        and path_key[: len(parent_key)] == parent_key
    )


def _paths_overlap(first: Path, second: Path) -> bool:
    return _is_within(first, second) or _is_within(second, first)


def _same_path(first: Path, second: Path) -> bool:
    """Compare existing paths without losing portable alias protection."""

    if _portable_absolute_path_key(first) == _portable_absolute_path_key(second):
        return True
    try:
        return first.samefile(second)
    except OSError:
        return False


def _ambient_opencode_write_roots(environment: Mapping[str, str]) -> tuple[Path, ...]:
    user_home = _resolved(_account_home())

    def xdg_root(name: str, default: Path) -> Path:
        raw = environment.get(name)
        if raw is None or raw == "":
            return _resolved(default)
        candidate = Path(raw)
        if not candidate.is_absolute():
            raise LifecycleError(f"{name} must be absolute when explicitly set")
        return _resolved(candidate)

    cache_home = xdg_root("XDG_CACHE_HOME", user_home / ".cache")
    data_home = xdg_root("XDG_DATA_HOME", user_home / ".local/share")
    state_home = xdg_root("XDG_STATE_HOME", user_home / ".local/state")
    return tuple(
        _resolved(path)
        for path in (cache_home, data_home / "opencode", state_home / "opencode")
    )


def _snapshot_opencode_auth(environment: Mapping[str, str]) -> str:
    """Read one bounded auth file snapshot without exposing it to a child."""

    if "OPENCODE_AUTH_CONTENT" in environment:
        raise LifecycleError(
            "OPENCODE_AUTH_CONTENT is owned by the managed launcher; configure "
            "auth.json or pass a provider credential variable instead"
        )
    raw_data_home = environment.get("XDG_DATA_HOME")
    if raw_data_home:
        data_home = Path(raw_data_home)
        if not data_home.is_absolute():
            raise LifecycleError("XDG_DATA_HOME must be absolute when explicitly set")
        data_home = _resolved(data_home)
    else:
        data_home = _resolved(_account_home()) / ".local/share"
    path = data_home / "opencode/auth.json"
    try:
        path.lstat()
    except FileNotFoundError:
        return "{}"
    except OSError as exc:
        raise LifecycleError(f"could not inspect OpenCode auth file {path}: {exc}") from exc

    content = _regular_file_bytes(
        path, label="OpenCode auth file", max_bytes=MAX_JSON_BYTES
    )
    auth = _parse_json_object(content, label="OpenCode auth file")
    for provider_id, entry in auth.items():
        if not isinstance(provider_id, str) or not provider_id:
            raise LifecycleError("OpenCode auth file contains an invalid provider ID")
    return json.dumps(
        auth, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def _validated_opencode_auth_entry(provider_id: str, entry: object) -> dict[str, Any]:
    if not isinstance(entry, dict):
        raise LifecycleError(f"OpenCode auth entry {provider_id!r} must be an object")
    auth_type = entry.get("type")
    if auth_type == "wellknown":
        raise LifecycleError(
            "managed OpenCode rejects selected wellknown auth because it fetches "
            "and merges remote executable configuration per process"
        )
    if auth_type == "api":
        allowed = {"type", "key", "metadata"}
        if set(entry) - allowed or not isinstance(entry.get("key"), str):
            raise LifecycleError(
                f"OpenCode API auth entry {provider_id!r} has an invalid shape"
            )
        metadata = entry.get("metadata")
        if metadata is not None and (
            not isinstance(metadata, dict)
            or any(
                not isinstance(key, str) or not isinstance(value, str)
                for key, value in metadata.items()
            )
        ):
            raise LifecycleError(
                f"OpenCode API auth entry {provider_id!r} has invalid metadata"
            )
    elif auth_type == "oauth":
        raise LifecycleError(
            "managed OpenCode rejects selected OAuth auth because custom "
            "OpenAI-compatible providers do not consume OpenCode's generic OAuth shape"
        )
    else:
        raise LifecycleError("selected OpenCode auth entry has unsupported type")
    # The managed custom OpenAI-compatible provider path consumes only the
    # generic API key.  Do not expose arbitrary account metadata to approved
    # child commands when it has no runtime consumer.
    return {"type": "api", "key": entry["key"]}


def _select_opencode_auth_for_resolved_providers(
    snapshot: str,
    resolved_config: Mapping[str, Any],
    selected_provider_ids: Sequence[str],
) -> str:
    """Expose only explicitly selected API credentials for admitted providers."""

    auth = _parse_json_object(snapshot.encode("utf-8"), label="OpenCode auth snapshot")
    providers = resolved_config.get("provider", {})
    if providers is None:
        providers = {}
    if not isinstance(providers, dict):
        raise LifecycleError("resolved OpenCode provider config must be an object")
    admitted: dict[str, dict[str, Any]] = {}
    for provider_id in selected_provider_ids:
        if provider_id not in providers:
            raise LifecycleError(
                f"selected auth provider {provider_id!r} is not an admitted "
                "custom provider in the resolved OpenCode config"
            )
        if provider_id not in auth:
            raise LifecycleError(
                f"selected auth provider {provider_id!r} is missing from auth.json"
            )
        provider = providers[provider_id]
        if not isinstance(provider, dict):
            raise LifecycleError("selected auth provider has an invalid config entry")
        options = provider.get("options")
        if isinstance(options, dict) and options.get("apiKey") is not None:
            raise LifecycleError(
                "selected auth provider duplicates an explicit provider apiKey; "
                "choose exactly one credential source"
            )
        admitted[provider_id] = _validated_opencode_auth_entry(
            provider_id, auth[provider_id]
        )
    return json.dumps(
        admitted, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def _provider_hostname_allowed(hostname: str, domains: Sequence[str]) -> bool:
    normalized = hostname.rstrip(".").lower()
    return any(
        normalized == domain or normalized.endswith("." + domain)
        for domain in domains
    )


def _sanitize_selected_provider(
    provider_id: str,
    provider: object,
    *,
    inputs: RuntimeInputs,
    environment: Mapping[str, str],
) -> dict[str, Any]:
    """Reduce one resolved provider to the reviewed, network-bound schema."""

    if not isinstance(provider, dict):
        raise LifecycleError(f"selected provider {provider_id!r} must be an object")
    allowed_provider_fields = {"npm", "name", "options", "models"}
    unsupported = sorted(set(provider) - allowed_provider_fields)
    if unsupported:
        raise LifecycleError(
            f"selected provider {provider_id!r} has unsupported managed fields"
        )
    if provider.get("npm") != SAFE_PROVIDER_NPM:
        raise LifecycleError(
            f"selected provider {provider_id!r} must use exactly {SAFE_PROVIDER_NPM!r}"
        )
    options = provider.get("options")
    if not isinstance(options, dict):
        raise LifecycleError(
            f"selected provider {provider_id!r} requires an options object"
        )
    unsupported_options = sorted(set(options) - {"baseURL", "apiKey"})
    if unsupported_options:
        raise LifecycleError(
            f"selected provider {provider_id!r} has unsupported credential/network "
            "options"
        )
    base_url = options.get("baseURL")
    if not isinstance(base_url, str) or not base_url:
        raise LifecycleError(
            f"selected provider {provider_id!r} requires an exact options.baseURL"
        )
    expected_base_url = dict(inputs.provider_base_urls).get(provider_id)
    if base_url != expected_base_url:
        raise LifecycleError(
            f"selected provider {provider_id!r} resolved baseURL differs from its "
            "explicit --provider-base-url contract"
        )
    try:
        parsed = urlsplit(base_url)
        port = parsed.port
    except ValueError as exc:
        raise LifecycleError(
            f"selected provider {provider_id!r} has an invalid baseURL"
        ) from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise LifecycleError(
            f"selected provider {provider_id!r} baseURL must be an uncredentialed "
            "HTTP(S) URL without query or fragment"
        )
    hostname = parsed.hostname.rstrip(".").lower()
    is_loopback = hostname == "localhost"
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None:
        is_loopback = address.is_loopback
        if not is_loopback:
            raise LifecycleError(
                f"selected provider {provider_id!r} forbids non-loopback IP literals"
            )
    effective_port = port or (443 if parsed.scheme == "https" else 80)
    local_route = is_loopback and effective_port in inputs.local_ports
    cloud_route = (
        parsed.scheme == "https"
        and effective_port == 443
        and address is None
        and _provider_hostname_allowed(hostname, inputs.provider_domains)
    )
    if inputs.profile.id in {"local", "local-only"} and not local_route:
        raise LifecycleError(
            f"selected provider {provider_id!r} baseURL is not the declared "
            "loopback host/port"
        )
    if inputs.profile.id == "cloud-open-weight" and not cloud_route:
        raise LifecycleError(
            f"selected provider {provider_id!r} baseURL is not HTTPS:443 under a "
            "declared public provider domain"
        )
    if inputs.profile.id == "hybrid" and not (local_route or cloud_route):
        raise LifecycleError(
            f"selected provider {provider_id!r} baseURL is outside the declared "
            "local and cloud routes"
        )

    assert expected_base_url is not None
    sanitized_options: dict[str, str] = {"baseURL": expected_base_url}
    api_key = options.get("apiKey")
    if api_key is not None:
        if not isinstance(api_key, str) or not api_key:
            raise LifecycleError(
                f"selected provider {provider_id!r} has an invalid apiKey"
            )
        matching_variables = [
            name
            for name in inputs.pass_environment
            if environment.get(name) == api_key
        ]
        if len(matching_variables) != 1:
            raise LifecycleError(
                f"selected provider {provider_id!r} apiKey must resolve exactly "
                "from one explicit --pass-env variable"
            )
        sanitized_options["apiKey"] = f"{{env:{matching_variables[0]}}}"

    models = provider.get("models")
    if not isinstance(models, dict) or not models:
        raise LifecycleError(
            f"selected provider {provider_id!r} requires at least one exact model"
        )
    selected_model_ids = tuple(
        model_id
        for selected_provider, model_id in inputs.provider_models
        if selected_provider == provider_id
    )
    missing_models = [model_id for model_id in selected_model_ids if model_id not in models]
    if missing_models:
        raise LifecycleError(
            f"selected provider {provider_id!r} is missing an explicit provider model"
        )
    sanitized_models: dict[str, dict[str, Any]] = {}
    for model_id in selected_model_ids:
        model = models[model_id]
        if not isinstance(model, dict):
            raise LifecycleError(
                f"selected provider {provider_id!r} contains an invalid model"
            )
        unsupported_model_fields = sorted(
            set(model)
            - {
                "name",
                "attachment",
                "reasoning",
                "temperature",
                "tool_call",
                "modalities",
                "limit",
            }
        )
        if unsupported_model_fields:
            raise LifecycleError(
                f"selected provider {provider_id!r} model {model_id!r} has "
                "unsupported managed fields"
            )
        sanitized_model: dict[str, Any] = {}
        for capability in (
            "attachment",
            "reasoning",
            "temperature",
            "tool_call",
        ):
            value = model.get(capability)
            if value is not None and not isinstance(value, bool):
                raise LifecycleError(
                    f"selected provider {provider_id!r} model {model_id!r} "
                    f"{capability} must be boolean"
                )
            if value is not None:
                sanitized_model[capability] = value
        modalities = model.get("modalities")
        if modalities is not None:
            if (
                not isinstance(modalities, dict)
                or set(modalities) - {"input", "output"}
                or any(
                    not isinstance(values, list)
                    or any(
                        value not in {"text", "audio", "image", "video", "pdf"}
                        for value in values
                    )
                    for values in modalities.values()
                )
            ):
                raise LifecycleError(
                    f"selected provider {provider_id!r} model {model_id!r} has "
                    "invalid modalities"
                )
            sanitized_model["modalities"] = modalities
        limits = model.get("limit")
        if (
            not isinstance(limits, dict)
            or set(limits) - {"context", "input", "output"}
            or not {"context", "output"}.issubset(limits)
            or any(type(value) is not int or value < 0 for value in limits.values())
            or limits["context"] <= 0
            or limits["output"] <= 0
        ):
            raise LifecycleError(
                f"selected provider {provider_id!r} model {model_id!r} requires "
                "positive limit.context and limit.output values"
            )
        sanitized_model["limit"] = limits
        sanitized_models[model_id] = sanitized_model

    sanitized: dict[str, Any] = {
        "npm": SAFE_PROVIDER_NPM,
        "options": sanitized_options,
        "models": sanitized_models,
    }
    return sanitized


def _select_resolved_providers(
    resolved_config: Mapping[str, Any],
    *,
    inputs: RuntimeInputs,
    environment: Mapping[str, str],
) -> dict[str, Any]:
    """Return the resolved config with only explicitly selected providers."""

    providers = resolved_config.get("provider", {})
    if providers is None:
        providers = {}
    if not isinstance(providers, dict):
        raise LifecycleError("resolved OpenCode provider config must be an object")
    missing = sorted(set(inputs.provider_ids) - set(providers))
    if missing:
        raise LifecycleError(
            "selected provider IDs are absent from resolved OpenCode config: "
            + ", ".join(missing)
        )
    selected = {
        provider_id: _sanitize_selected_provider(
            provider_id,
            providers[provider_id],
            inputs=inputs,
            environment=environment,
        )
        for provider_id in inputs.provider_ids
    }
    filtered = dict(resolved_config)
    filtered["provider"] = selected
    agents = filtered.get("agent")
    if isinstance(agents, dict):
        selected_model_references = {
            f"{provider_id}/{model_id}": f"{provider_id}/{model_id}"
            for provider_id, model_id in inputs.provider_models
        }
        for agent_id, entry in agents.items():
            if not isinstance(entry, dict):
                continue
            model = entry.get("model")
            if entry.get("variant") is not None:
                raise LifecycleError(
                    "resolved agent variant override is unsupported for the narrow "
                    "managed custom-provider schema"
                )
            if model is None:
                continue
            if not isinstance(model, str) or model not in selected_model_references:
                raise LifecycleError(
                    "resolved agent model override must use an exact "
                    "--provider-model selection"
                )
            # Reconstruct the reference from the launcher-owned selection.  Do
            # not carry arbitrary resolved strings (which OpenCode may have
            # expanded from {file:...} or {env:...}) into child environment.
            entry["model"] = selected_model_references[model]
    return filtered


def _validate_lifecycle_locations(
    home: Path,
    runtime_root: Path,
    environment: Mapping[str, str],
) -> tuple[Path, Path]:
    resolved_home = _resolved(home)
    resolved_runtime = _resolved(runtime_root)
    managed_runtime = resolved_home / "runtime"
    if not _is_within(resolved_runtime, managed_runtime):
        raise LifecycleError(
            "runtime root must be inside the lifecycle-owned directory "
            f"{managed_runtime}; paths such as ~/.cache are ambient-writable in cplt"
        )

    project_root = _resolved(_project_root(environment))
    if _paths_overlap(resolved_home, project_root):
        raise LifecycleError(
            "lifecycle home must not overlap cplt's writable project directory: "
            f"home={resolved_home}, project={project_root}"
        )
    for ambient_root in _ambient_opencode_write_roots(environment):
        if _paths_overlap(resolved_home, ambient_root):
            raise LifecycleError(
                "lifecycle home is inside an ambient cplt/OpenCode write area and "
                f"cannot protect staged policy as read-only: {ambient_root}"
            )
    return resolved_home, resolved_runtime


def _require_audited_cplt_home(home: Path) -> None:
    """Keep immutable policy outside every built-in cplt write namespace."""

    account_home = _resolved(_account_home())
    expected = account_home / ".local/share/grillmester/opencode"
    if home != expected:
        raise LifecycleError(
            "cplt launches require the audited lifecycle home "
            f"{expected}; custom/XDG homes are supported only with --direct"
        )
    current = account_home
    for part in (".local", "share", "grillmester", "opencode"):
        current /= part
        if current.exists() or current.is_symlink():
            _inspect_owned_directory(current, label="audited cplt lifecycle ancestor")


def _inspect_owned_directory(path: Path, *, label: str) -> bool:
    try:
        path_stat = path.lstat()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise LifecycleError(f"could not inspect {label} {path}: {exc}") from exc
    if stat.S_ISLNK(path_stat.st_mode):
        raise LifecycleError(f"refusing to use symlinked {label}: {path}")
    if not stat.S_ISDIR(path_stat.st_mode):
        raise LifecycleError(f"{label} is not a directory: {path}")
    if hasattr(os, "geteuid") and path_stat.st_uid != os.geteuid():
        raise LifecycleError(f"{label} is not owned by the current user: {path}")
    return True


def _ensure_owned_directory(path: Path, *, label: str, mode: int = 0o700) -> None:
    if not _inspect_owned_directory(path, label=label):
        try:
            path.mkdir(parents=True, mode=mode)
        except OSError as exc:
            raise LifecycleError(f"could not create {label} {path}: {exc}") from exc
        if not _inspect_owned_directory(path, label=label):  # pragma: no cover
            raise LifecycleError(f"could not create {label}: {path}")
    try:
        path.chmod(mode)
    except OSError as exc:
        raise LifecycleError(f"could not secure {label} {path}: {exc}") from exc


def _regular_file(
    path: Path, *, label: str, max_bytes: int = MAX_FILE_BYTES
) -> tuple[bytes, os.stat_result]:
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError as exc:
        raise LifecycleError(f"missing {label}: {path}") from exc
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise LifecycleError(f"refusing to read symlinked {label}: {path}") from exc
        raise LifecycleError(f"could not open {label} {path}: {exc}") from exc
    try:
        observed = os.fstat(descriptor)
    except OSError as exc:
        os.close(descriptor)
        raise LifecycleError(f"could not inspect {label} {path}: {exc}") from exc
    if not stat.S_ISREG(observed.st_mode):
        os.close(descriptor)
        raise LifecycleError(f"{label} is not a regular file: {path}")
    if observed.st_size > max_bytes:
        os.close(descriptor)
        raise LifecycleError(
            f"{label} exceeds the {max_bytes}-byte safety limit: {path}"
        )
    try:
        with os.fdopen(descriptor, "rb", closefd=True) as source:
            content = source.read(max_bytes + 1)
            if len(content) > max_bytes:
                raise LifecycleError(
                    f"{label} exceeds the {max_bytes}-byte safety limit: {path}"
                )
            return content, observed
    except OSError as exc:
        raise LifecycleError(f"could not read {label} {path}: {exc}") from exc


def _regular_file_bytes(
    path: Path, *, label: str, max_bytes: int = MAX_FILE_BYTES
) -> bytes:
    content, _ = _regular_file(path, label=label, max_bytes=max_bytes)
    return content


def _portable_collision_key(path: PurePosixPath) -> str:
    return unicodedata.normalize("NFC", path.as_posix()).casefold()


def _parse_manifest_path(value: object) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise LifecycleError("manifest file paths must be non-empty strings")
    if "\\" in value or any(
        ord(character) < 32 or ord(character) == 127 for character in value
    ):
        raise LifecycleError(f"manifest path is not portable: {value!r}")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or value != path.as_posix()
        or any(part in ("", ".", "..") for part in path.parts)
        or path == PurePosixPath("manifest.json")
    ):
        raise LifecycleError(f"unsafe manifest path: {value!r}")
    return path


def _parse_manifest(
    root: Path,
) -> tuple[bytes, tuple[ManifestEntry, ...], os.stat_result]:
    manifest_bytes, manifest_stat = _regular_file(
        root / "manifest.json", label="target manifest", max_bytes=MAX_JSON_BYTES
    )
    manifest = _parse_json_object(manifest_bytes, label="target manifest")
    if type(manifest.get("schemaVersion")) is not int or manifest["schemaVersion"] != 1:
        raise LifecycleError("target manifest schemaVersion must be 1")
    if manifest.get("target") != TARGET_NAME:
        raise LifecycleError(f"target manifest must name {TARGET_NAME!r}")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise LifecycleError("target manifest files must be a non-empty object")
    if len(files) + 2 > MAX_DISTRIBUTION_MEMBERS:
        raise LifecycleError(
            "target manifest exceeds the "
            f"{MAX_DISTRIBUTION_MEMBERS}-member safety limit"
        )

    entries: list[ManifestEntry] = []
    seen: set[PurePosixPath] = set()
    seen_portable: set[str] = set()
    for raw_relative, raw_entry in files.items():
        relative = _parse_manifest_path(raw_relative)
        if relative in seen:
            raise LifecycleError(f"duplicate manifest path: {relative}")
        seen.add(relative)
        portable_key = _portable_collision_key(relative)
        if portable_key in seen_portable:
            raise LifecycleError(
                f"portable manifest path collision: {relative}"
            )
        seen_portable.add(portable_key)
        if not isinstance(raw_entry, dict) or set(raw_entry) != {"sha256", "mode"}:
            raise LifecycleError(
                f"manifest entry for {relative} must contain only sha256 and mode"
            )
        digest = raw_entry.get("sha256")
        mode = raw_entry.get("mode")
        if not isinstance(digest, str) or not RELEASE_ID_PATTERN.fullmatch(digest):
            raise LifecycleError(f"invalid sha256 for manifest entry {relative}")
        if not isinstance(mode, str) or not re.fullmatch(r"0[0-7]{3}", mode):
            raise LifecycleError(f"invalid mode for manifest entry {relative}")
        parsed_mode = int(mode, 8)
        if parsed_mode not in ALLOWED_BUNDLE_MODES:
            raise LifecycleError(
                f"unsupported mode for manifest entry {relative}: {mode}"
            )
        entries.append(ManifestEntry(relative, digest, parsed_mode))
    entries.sort(key=lambda entry: entry.relative.as_posix())
    return manifest_bytes, tuple(entries), manifest_stat


def _bundle_inventory(
    root: Path, *, excluded: PurePosixPath = PurePosixPath("manifest.json")
) -> set[PurePosixPath]:
    inventory: set[PurePosixPath] = set()
    portable_nodes: dict[str, PurePosixPath] = {}
    node_count = 1
    try:
        root_stat = root.lstat()
    except FileNotFoundError as exc:
        raise LifecycleError(f"bundle directory does not exist: {root}") from exc
    except OSError as exc:
        raise LifecycleError(f"could not inspect bundle directory {root}: {exc}") from exc
    if stat.S_ISLNK(root_stat.st_mode):
        raise LifecycleError(f"refusing to use symlinked bundle directory: {root}")
    if not stat.S_ISDIR(root_stat.st_mode):
        raise LifecycleError(f"bundle path is not a directory: {root}")

    def walk_error(error: OSError) -> None:
        raise LifecycleError(f"could not inventory bundle {root}: {error}")

    for current, directories, files in os.walk(
        root, followlinks=False, onerror=walk_error
    ):
        node_count += len(directories) + len(files)
        if node_count > MAX_DISTRIBUTION_MEMBERS:
            raise LifecycleError(
                "bundle exceeds the "
                f"{MAX_DISTRIBUTION_MEMBERS}-member safety limit"
            )
        current_path = Path(current)
        for name in list(directories):
            child = current_path / name
            child_stat = child.lstat()
            if stat.S_ISLNK(child_stat.st_mode):
                raise LifecycleError(f"bundle contains a symlinked directory: {child}")
            if not stat.S_ISDIR(child_stat.st_mode):
                raise LifecycleError(f"bundle contains a non-directory node: {child}")
            relative = PurePosixPath(child.relative_to(root).as_posix())
            collision_key = _portable_collision_key(relative)
            previous = portable_nodes.get(collision_key)
            if previous is not None and previous != relative:
                raise LifecycleError(
                    f"bundle contains a portable path collision: {previous}, {relative}"
                )
            portable_nodes[collision_key] = relative
        for name in files:
            child = current_path / name
            child_stat = child.lstat()
            if stat.S_ISLNK(child_stat.st_mode):
                raise LifecycleError(f"bundle contains a symlink: {child}")
            if not stat.S_ISREG(child_stat.st_mode):
                raise LifecycleError(f"bundle contains a non-regular file: {child}")
            relative = PurePosixPath(child.relative_to(root).as_posix())
            collision_key = _portable_collision_key(relative)
            previous = portable_nodes.get(collision_key)
            if previous is not None and previous != relative:
                raise LifecycleError(
                    f"bundle contains a portable path collision: {previous}, {relative}"
                )
            portable_nodes[collision_key] = relative
            if relative != excluded:
                inventory.add(relative)
    return inventory


def verify_bundle(root: Path, *, immutable: bool) -> VerifiedBundle:
    """Verify exact inventory, content and modes; return trusted metadata."""

    manifest_bytes, entries, manifest_stat = _parse_manifest(root)
    expected = {entry.relative for entry in entries}
    actual = _bundle_inventory(root)
    missing = sorted(expected - actual, key=str)
    extras = sorted(actual - expected, key=str)
    if missing:
        raise LifecycleError(
            "bundle is missing manifest files: " + ", ".join(map(str, missing))
        )
    if extras:
        raise LifecycleError(
            "bundle contains unmanifested files: " + ", ".join(map(str, extras))
        )

    aggregate_size = len(manifest_bytes)
    for entry in entries:
        path = root.joinpath(*entry.relative.parts)
        content, observed_stat = _regular_file(
            path, label=f"bundle file {entry.relative}"
        )
        observed_digest = _sha256(content)
        aggregate_size += len(content)
        if aggregate_size > MAX_DISTRIBUTION_BYTES:
            raise LifecycleError(
                f"bundle exceeds the {MAX_DISTRIBUTION_BYTES}-byte safety limit"
            )
        if observed_digest != entry.sha256:
            raise LifecycleError(
                f"checksum mismatch for {entry.relative}: expected {entry.sha256}, "
                f"observed {observed_digest}"
            )
        observed_mode = stat.S_IMODE(observed_stat.st_mode)
        expected_mode = entry.mode & ~0o222 if immutable else entry.mode
        if observed_mode != expected_mode:
            raise LifecycleError(
                f"mode mismatch for {entry.relative}: expected {expected_mode:04o}, "
                f"observed {observed_mode:04o}"
            )
    manifest_mode = stat.S_IMODE(manifest_stat.st_mode)
    if immutable and manifest_mode != 0o444:
        raise LifecycleError(
            f"mode mismatch for manifest.json: expected 0444, observed {manifest_mode:04o}"
        )
    if not immutable and manifest_mode != 0o644:
        raise LifecycleError(
            f"mode mismatch for manifest.json: expected 0644, observed {manifest_mode:04o}"
        )
    return VerifiedBundle(
        root=root,
        manifest_bytes=manifest_bytes,
        release_id=_sha256(manifest_bytes),
        entries=entries,
    )


def _parse_distribution_manifest(
    root: Path, *, require_current_contract: bool
) -> tuple[bytes, tuple[ManifestEntry, ...], os.stat_result, dict[str, Any]]:
    manifest_path = root / DISTRIBUTION_MANIFEST
    manifest_bytes, manifest_stat = _regular_file(
        manifest_path,
        label="distribution manifest",
        max_bytes=MAX_JSON_BYTES,
    )
    manifest = _parse_json_object(manifest_bytes, label="distribution manifest")
    expected_fields = {
        "schemaVersion",
        "sourceSha",
        "target",
        "opencodeVersion",
        "cpltRelease",
        "targetManifestSha256",
        "files",
    }
    if set(manifest) != expected_fields:
        raise LifecycleError("distribution manifest has unexpected or missing fields")
    if type(manifest.get("schemaVersion")) is not int or manifest["schemaVersion"] != 1:
        raise LifecycleError("distribution manifest schemaVersion must be 1")
    if (
        not isinstance(manifest.get("sourceSha"), str)
        or SOURCE_SHA_PATTERN.fullmatch(manifest["sourceSha"]) is None
    ):
        raise LifecycleError("distribution manifest sourceSha must be 40 lowercase hex")
    if manifest.get("target") != TARGET_NAME:
        raise LifecycleError(f"distribution manifest must name {TARGET_NAME!r}")
    opencode_version = manifest.get("opencodeVersion")
    cplt_release = manifest.get("cpltRelease")
    if not isinstance(opencode_version, str) or not opencode_version.strip():
        raise LifecycleError("distribution opencodeVersion must be a non-empty string")
    if not isinstance(cplt_release, str) or not cplt_release.strip():
        raise LifecycleError("distribution cpltRelease must be a non-empty string")
    if require_current_contract and opencode_version != SUPPORTED_OPENCODE_VERSION:
        raise LifecycleError(
            f"distribution must pin OpenCode {SUPPORTED_OPENCODE_VERSION}"
        )
    if require_current_contract and cplt_release != SUPPORTED_CPLT_RELEASE:
        raise LifecycleError(f"distribution must pin cplt {SUPPORTED_CPLT_RELEASE}")
    target_manifest_digest = manifest.get("targetManifestSha256")
    if (
        not isinstance(target_manifest_digest, str)
        or RELEASE_ID_PATTERN.fullmatch(target_manifest_digest) is None
    ):
        raise LifecycleError("distribution targetManifestSha256 is invalid")

    raw_files = manifest.get("files")
    if not isinstance(raw_files, dict) or not raw_files:
        raise LifecycleError("distribution manifest files must be a non-empty object")
    if len(raw_files) + 2 > MAX_DISTRIBUTION_MEMBERS:
        raise LifecycleError(
            "distribution manifest exceeds the "
            f"{MAX_DISTRIBUTION_MEMBERS}-member safety limit"
        )
    entries: list[ManifestEntry] = []
    seen_portable: set[str] = set()
    for raw_relative, raw_entry in raw_files.items():
        relative = _parse_manifest_path(raw_relative)
        if relative == PurePosixPath(DISTRIBUTION_MANIFEST):
            raise LifecycleError("distribution manifest must not describe itself")
        portable_key = _portable_collision_key(relative)
        if portable_key in seen_portable:
            raise LifecycleError(f"portable distribution path collision: {relative}")
        seen_portable.add(portable_key)
        if not isinstance(raw_entry, dict) or set(raw_entry) != {"sha256", "mode"}:
            raise LifecycleError(
                f"distribution entry for {relative} must contain only sha256 and mode"
            )
        digest = raw_entry.get("sha256")
        raw_mode = raw_entry.get("mode")
        if not isinstance(digest, str) or RELEASE_ID_PATTERN.fullmatch(digest) is None:
            raise LifecycleError(f"invalid sha256 for distribution entry {relative}")
        if not isinstance(raw_mode, str) or re.fullmatch(r"0[0-7]{3}", raw_mode) is None:
            raise LifecycleError(f"invalid mode for distribution entry {relative}")
        mode = int(raw_mode, 8)
        if mode not in ALLOWED_BUNDLE_MODES:
            raise LifecycleError(
                f"unsupported mode for distribution entry {relative}: {raw_mode}"
            )
        entries.append(ManifestEntry(relative, digest, mode))
    entries.sort(key=lambda entry: entry.relative.as_posix())
    return manifest_bytes, tuple(entries), manifest_stat, manifest


def verify_distribution(
    root: Path, *, immutable: bool, require_current_contract: bool = True
) -> VerifiedDistribution:
    """Verify the complete published distribution, including profiles and target."""

    manifest_bytes, entries, manifest_stat, manifest = _parse_distribution_manifest(
        root, require_current_contract=require_current_contract
    )
    expected = {entry.relative for entry in entries}
    actual = _bundle_inventory(
        root, excluded=PurePosixPath(DISTRIBUTION_MANIFEST)
    )
    missing = sorted(expected - actual, key=str)
    extras = sorted(actual - expected, key=str)
    if missing:
        raise LifecycleError(
            "distribution is missing manifest files: " + ", ".join(map(str, missing))
        )
    if extras:
        raise LifecycleError(
            "distribution contains unmanifested files: " + ", ".join(map(str, extras))
        )

    required_profiles = {
        PROFILE_RELATIVE / f"{profile_id}.json" for profile_id in PROFILE_SHAPES
    }
    required = {
        MANAGER_RELATIVE,
        TARGET_RELATIVE / "manifest.json",
        *required_profiles,
    }
    if require_current_contract:
        required.update(
            {
                PERMISSION_COMPOSER_RELATIVE,
                ARTIFACT_VERIFIER_RELATIVE,
                CLIENT_ARTIFACTS_RELATIVE,
                CONTENT_LOCK_RELATIVE,
                LICENSE_RELATIVE,
                PROVENANCE_RELATIVE,
                THIRD_PARTY_NOTICES_RELATIVE,
            }
        )
    absent_required = sorted(required - expected, key=str)
    if absent_required:
        raise LifecycleError(
            "distribution omits required runtime files: "
            + ", ".join(map(str, absent_required))
        )
    observed_profiles = {
        path
        for path in expected
        if path.parent == PROFILE_RELATIVE and path.suffix == ".json"
    }
    if observed_profiles != required_profiles:
        raise LifecycleError("distribution must contain exactly four runtime profiles")
    if require_current_contract:
        manager_digest = next(
            entry.sha256
            for entry in entries
            if entry.relative == MANAGER_RELATIVE
        )
        current_manager_digest = _sha256(
            _regular_file_bytes(
                Path(__file__).resolve(strict=True), label="current lifecycle manager"
            )
        )
        if manager_digest != current_manager_digest:
            raise LifecycleError(
                "distribution lifecycle manager differs from the executing manager"
            )
        composer_digest = next(
            entry.sha256
            for entry in entries
            if entry.relative == PERMISSION_COMPOSER_RELATIVE
        )
        if composer_digest != PERMISSION_COMPOSER_SHA256:
            raise LifecycleError(
                "distribution permission composer differs from the manager-pinned code"
            )

    aggregate_size = len(manifest_bytes)
    for entry in entries:
        content, observed_stat = _regular_file(
            root.joinpath(*entry.relative.parts),
            label=f"distribution file {entry.relative}",
        )
        aggregate_size += len(content)
        if aggregate_size > MAX_DISTRIBUTION_BYTES:
            raise LifecycleError(
                f"distribution exceeds the {MAX_DISTRIBUTION_BYTES}-byte safety limit"
            )
        if _sha256(content) != entry.sha256:
            raise LifecycleError(f"checksum mismatch for distribution file {entry.relative}")
        observed_mode = stat.S_IMODE(observed_stat.st_mode)
        expected_mode = entry.mode & ~0o222 if immutable else entry.mode
        if observed_mode != expected_mode:
            raise LifecycleError(
                f"mode mismatch for distribution file {entry.relative}: "
                f"expected {expected_mode:04o}, observed {observed_mode:04o}"
            )
    manifest_mode = stat.S_IMODE(manifest_stat.st_mode)
    expected_manifest_mode = 0o444 if immutable else 0o644
    if manifest_mode != expected_manifest_mode:
        raise LifecycleError(
            f"mode mismatch for {DISTRIBUTION_MANIFEST}: expected "
            f"{expected_manifest_mode:04o}, observed {manifest_mode:04o}"
        )

    target_root = root.joinpath(*TARGET_RELATIVE.parts)
    target = verify_bundle(target_root, immutable=immutable)
    if _sha256(target.manifest_bytes) != manifest["targetManifestSha256"]:
        raise LifecycleError("distribution target manifest digest does not match target")
    if require_current_contract:
        content_lock = _parse_json_object(
            _regular_file_bytes(
                root.joinpath(*CONTENT_LOCK_RELATIVE.parts), label="content lock"
            ),
            label="content lock",
        )
        agents = content_lock.get("agents")
        skills = content_lock.get("skills")
        if (
            set(content_lock) != {"schemaVersion", "sources", "agents", "skills"}
            or type(content_lock.get("schemaVersion")) is not int
            or content_lock["schemaVersion"] != 1
            or not isinstance(agents, dict)
            or set(agents) != MANAGED_AGENT_IDS
            or not isinstance(skills, dict)
            or len(skills) != 42
            or any(not isinstance(skill_id, str) or not skill_id for skill_id in skills)
        ):
            raise LifecycleError("content lock must contain the reviewed 7/42 roster")
        target_manifest = _parse_json_object(
            target.manifest_bytes, label="target manifest"
        )
        target_paths = {entry.relative for entry in target.entries}
        expected_agent_paths = {
            PurePosixPath("agents") / f"{agent_id}.md"
            for agent_id in MANAGED_AGENT_IDS
        }
        observed_agent_paths = {
            path for path in target_paths if path.parts[:1] == ("agents",)
        }
        expected_skills = frozenset(skills)
        expected_skill_paths = {
            PurePosixPath("skills") / skill_id / "SKILL.md"
            for skill_id in expected_skills
        }
        observed_skill_paths = {
            path
            for path in target_paths
            if len(path.parts) == 3
            and path.parts[0] == "skills"
            and path.name == "SKILL.md"
        }
        observed_skill_ids = {
            path.parts[1]
            for path in target_paths
            if len(path.parts) >= 2 and path.parts[0] == "skills"
        }
        expected_command_paths = {
            PurePosixPath("commands") / f"{skill_id}.md"
            for skill_id in expected_skills
        }
        observed_command_paths = {
            path for path in target_paths if path.parts[:1] == ("commands",)
        }
        if (
            observed_agent_paths != expected_agent_paths
            or observed_skill_paths != expected_skill_paths
            or observed_skill_ids != expected_skills
            or observed_command_paths != expected_command_paths
        ):
            raise LifecycleError(
                "target must contain the exact reviewed 7-agent/42-skill/42-command roster"
            )
        if target_manifest.get("counts") != {
            "agents": 7,
            "primaryAgents": 4,
            "subagents": 3,
            "skills": 42,
            "commands": 42,
        }:
            raise LifecycleError("target manifest has the wrong 7/42/42 counts")
        capabilities = target_manifest.get("skillCapabilities")
        expected_capabilities = {
            skill_id: (
                "overlay" if skill_id in OPENCODE_OVERLAY_SKILL_IDS else "native"
            )
            for skill_id in expected_skills
        }
        if capabilities != expected_capabilities:
            raise LifecycleError(
                "target skillCapabilities differ from the reviewed classification"
            )
    profile_root = root.joinpath(*PROFILE_RELATIVE.parts)
    if require_current_contract:
        for profile_id in sorted(PROFILE_SHAPES):
            load_profile(profile_id, profile_root=profile_root)
    return VerifiedDistribution(
        root=root,
        manifest_bytes=manifest_bytes,
        release_id=_sha256(manifest_bytes),
        entries=entries,
        target=target,
    )


def _write_verified_file(source: Path, destination: Path, entry: ManifestEntry) -> None:
    content = _regular_file_bytes(source, label=f"bundle file {entry.relative}")
    if _sha256(content) != entry.sha256:
        raise LifecycleError(f"checksum changed while copying {entry.relative}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("xb") as output:
            output.write(content)
        destination.chmod(entry.mode)
    except OSError as exc:
        raise LifecycleError(f"could not copy bundle file {entry.relative}: {exc}") from exc


def _copy_bundle(bundle: VerifiedBundle, destination: Path, *, immutable: bool) -> None:
    try:
        destination.mkdir(parents=True)
        for entry in bundle.entries:
            source = bundle.root.joinpath(*entry.relative.parts)
            target = destination.joinpath(*entry.relative.parts)
            _write_verified_file(source, target, entry)
        manifest_path = destination / "manifest.json"
        with manifest_path.open("xb") as output:
            output.write(bundle.manifest_bytes)
        manifest_path.chmod(0o644)
        if immutable:
            for entry in bundle.entries:
                destination.joinpath(*entry.relative.parts).chmod(entry.mode & ~0o222)
            manifest_path.chmod(0o444)
            directories = [path for path in destination.rglob("*") if path.is_dir()]
            for directory in sorted(directories, key=lambda path: len(path.parts), reverse=True):
                directory.chmod(0o555)
            destination.chmod(0o555)
    except LifecycleError:
        raise
    except OSError as exc:
        raise LifecycleError(f"could not stage bundle at {destination}: {exc}") from exc


def _stage_opencode_runtime_support(config: Path) -> dict[PurePosixPath, str]:
    """Pre-seed OpenCode's write-if-absent metadata without making policy writable."""

    path = config.joinpath(*OPENCODE_RUNTIME_GITIGNORE_PATH.parts)
    try:
        with path.open("xb") as output:
            output.write(OPENCODE_RUNTIME_GITIGNORE)
        path.chmod(0o444)
    except OSError as exc:
        raise LifecycleError(
            f"could not stage OpenCode runtime support file: {exc}"
        ) from exc
    content, observed = _regular_file(
        path,
        label="staged OpenCode runtime support file",
        max_bytes=MAX_FILE_BYTES,
    )
    if (
        content != OPENCODE_RUNTIME_GITIGNORE
        or stat.S_IMODE(observed.st_mode) != 0o444
    ):
        raise LifecycleError("OpenCode runtime support file changed while staging")
    return {OPENCODE_RUNTIME_GITIGNORE_PATH: _sha256(content)}


def _stage_ambient_xdg_config_snapshot(
    environment: Mapping[str, str], destination: Path
) -> dict[PurePosixPath, str]:
    """Copy only OpenCode's three declarative global config files for probing."""

    source_root = _resolved(
        Path(environment["XDG_CONFIG_HOME"]) / "opencode"
    )
    try:
        destination.mkdir(mode=0o700)
    except OSError as exc:
        raise LifecycleError("could not create ambient XDG config snapshot") from exc
    staged: dict[PurePosixPath, str] = {}
    if _inspect_owned_directory(source_root, label="ambient OpenCode XDG config root"):
        for filename in ("config.json", "opencode.json", "opencode.jsonc"):
            source = source_root / filename
            if not source.exists() and not source.is_symlink():
                continue
            content = _regular_file_bytes(
                source,
                label="ambient OpenCode XDG config",
                max_bytes=MAX_FILE_BYTES,
            )
            relative = PurePosixPath(filename)
            target = destination / filename
            try:
                with target.open("xb") as output:
                    output.write(content)
                target.chmod(0o444)
            except OSError as exc:
                raise LifecycleError(
                    "could not stage ambient OpenCode XDG config snapshot"
                ) from exc
            staged[relative] = _sha256(content)
    staged.update(_stage_opencode_runtime_support(destination))
    try:
        destination.chmod(0o500)
    except OSError as exc:
        raise LifecycleError("could not seal ambient XDG config snapshot") from exc
    return staged


def _shorten_agent_for_config_probe(content: bytes, relative: PurePosixPath) -> bytes:
    """Keep exact frontmatter while bounding OpenCode's resolved-config output."""

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LifecycleError(f"config probe agent is not UTF-8: {relative}") from exc
    end = text.find("\n---\n", 4)
    if not text.startswith("---\n") or end < 0:
        raise LifecycleError(f"config probe agent lacks canonical frontmatter: {relative}")
    agent_id = relative.stem
    return (
        text[: end + len("\n---\n")]
        + f"\n{OPENCODE_CONFIG_PROBE_MARKER} for {agent_id}.\n"
    ).encode("utf-8")


def _shorten_skill_for_config_probe(content: bytes, relative: PurePosixPath) -> bytes:
    """Keep exact skill frontmatter while bounding ``debug skill`` output."""

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LifecycleError(f"config probe skill is not UTF-8: {relative}") from exc
    end = text.find("\n---\n", 4)
    if not text.startswith("---\n") or end < 0:
        raise LifecycleError(f"config probe skill lacks canonical frontmatter: {relative}")
    skill_id = relative.parts[1]
    return (
        text[: end + len("\n---\n")]
        + f"{OPENCODE_SKILL_PROBE_MARKER} for {skill_id}.\n"
    ).encode("utf-8")


def _project_config_probe_file(content: bytes, relative: PurePosixPath) -> bytes:
    """Apply the sole reviewed lossy transforms used by the probe clone."""

    if (
        len(relative.parts) == 2
        and relative.parts[0] == "agents"
        and relative.suffix == ".md"
    ):
        return _shorten_agent_for_config_probe(content, relative)
    if (
        len(relative.parts) == 3
        and relative.parts[0] == "skills"
        and relative.parts[2] == "SKILL.md"
    ):
        return _shorten_skill_for_config_probe(content, relative)
    return content


def _validate_sealed_config_probe(
    root: Path, expected_files: Mapping[PurePosixPath, str]
) -> str:
    """Require one exact read-only probe tree and return its stable fingerprint."""

    no_exclusion = PurePosixPath(".grillmester-no-excluded-manifest")
    actual = _bundle_inventory(root, excluded=no_exclusion)
    if actual != set(expected_files):
        raise LifecycleError("bounded OpenCode config probe inventory changed")
    directories = [root, *(path for path in root.rglob("*") if path.is_dir())]
    for directory in directories:
        observed = directory.lstat()
        if (
            not stat.S_ISDIR(observed.st_mode)
            or stat.S_IMODE(observed.st_mode) != 0o555
        ):
            raise LifecycleError("bounded OpenCode config probe directory is not 0555")
    canonical: list[tuple[str, str]] = []
    for relative, expected_digest in sorted(
        expected_files.items(), key=lambda item: item[0].as_posix()
    ):
        content, observed = _regular_file(
            root.joinpath(*relative.parts),
            label="bounded OpenCode config probe file",
            max_bytes=MAX_FILE_BYTES,
        )
        if (
            stat.S_IMODE(observed.st_mode) != 0o444
            or _sha256(content) != expected_digest
        ):
            raise LifecycleError("bounded OpenCode config probe file changed")
        canonical.append((relative.as_posix(), expected_digest))
    serialized = json.dumps(canonical, separators=(",", ":"))
    return _sha256(serialized.encode("utf-8"))


def _stage_bounded_config_probe(
    source: Path,
    destination: Path,
    *,
    expected_inventory: frozenset[PurePosixPath],
) -> tuple[
    dict[PurePosixPath, str], dict[PurePosixPath, str], str
]:
    """Clone composed config below pinned Bun's piped-stdout flush boundary."""

    actual = _bundle_inventory(source)
    if actual != set(expected_inventory):
        raise LifecycleError("composed config inventory changed before probe staging")
    try:
        destination.mkdir(mode=0o700)
        source_files: dict[PurePosixPath, str] = {}
        files: dict[PurePosixPath, str] = {}
        for relative in sorted(
            {*actual, PurePosixPath("manifest.json")},
            key=PurePosixPath.as_posix,
        ):
            content = _regular_file_bytes(
                source.joinpath(*relative.parts),
                label="composed config probe source",
                max_bytes=MAX_FILE_BYTES,
            )
            source_files[relative] = _sha256(content)
            content = _project_config_probe_file(content, relative)
            output = destination.joinpath(*relative.parts)
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("xb") as handle:
                handle.write(content)
            output.chmod(0o444)
            files[relative] = _sha256(content)
        directories = [path for path in destination.rglob("*") if path.is_dir()]
        for directory in sorted(
            directories, key=lambda path: len(path.parts), reverse=True
        ):
            directory.chmod(0o555)
        destination.chmod(0o555)
    except LifecycleError:
        raise
    except OSError as exc:
        raise LifecycleError(f"could not stage bounded OpenCode config probe: {exc}") from exc
    fingerprint = _validate_sealed_config_probe(destination, files)
    return source_files, files, fingerprint


def _validate_config_probe_projection(
    source: Path,
    probe: Path,
    *,
    expected_inventory: frozenset[PurePosixPath],
    expected_source_files: Mapping[PurePosixPath, str],
    expected_probe_files: Mapping[PurePosixPath, str],
) -> str:
    """Bind every probe byte to the current sealed real config projection."""

    actual = _bundle_inventory(source)
    if actual != set(expected_inventory):
        raise LifecycleError("sealed composed config inventory changed")
    directories = [source, *(path for path in source.rglob("*") if path.is_dir())]
    for directory in directories:
        observed = directory.lstat()
        if (
            not stat.S_ISDIR(observed.st_mode)
            or stat.S_IMODE(observed.st_mode) != 0o555
        ):
            raise LifecycleError("sealed composed config directory is not 0555")
    expected_paths = {*actual, PurePosixPath("manifest.json")}
    if set(expected_source_files) != expected_paths:
        raise LifecycleError("bounded config probe lost its source binding")
    if set(expected_probe_files) != expected_paths:
        raise LifecycleError("bounded config probe no longer covers every source file")
    for relative in sorted(expected_paths, key=PurePosixPath.as_posix):
        content, observed = _regular_file(
            source.joinpath(*relative.parts),
            label="sealed composed config projection source",
            max_bytes=MAX_FILE_BYTES,
        )
        if observed.st_mode & 0o222:
            raise LifecycleError("sealed composed config file became writable")
        if _sha256(content) != expected_source_files[relative]:
            raise LifecycleError("sealed composed config projection source changed")
        content = _project_config_probe_file(content, relative)
        if _sha256(content) != expected_probe_files[relative]:
            raise LifecycleError("bounded config probe diverged from real config")
    return _validate_sealed_config_probe(probe, expected_probe_files)


def _seal_composed_runtime_config(
    config: Path,
    bundle: VerifiedBundle,
    extra_files: Mapping[PurePosixPath, str] | None = None,
) -> None:
    """Make an already verified, policy-composed target tree read-only."""

    try:
        expected = {entry.relative: entry.mode for entry in bundle.entries}
        extras = dict(extra_files or {})
        if set(extras) & (set(expected) | {PurePosixPath("manifest.json")}):
            raise LifecycleError("composed runtime extra files collide with target files")
        actual = _bundle_inventory(config)
        if actual != set(expected) | set(extras):
            raise LifecycleError(
                "composed runtime config changed its verified file inventory"
            )
        for relative, mode in expected.items():
            config.joinpath(*relative.parts).chmod(mode & ~0o222)
        for relative, digest in extras.items():
            path = config.joinpath(*relative.parts)
            content = _regular_file_bytes(
                path,
                label="staged config extra",
                max_bytes=MAX_FILE_BYTES,
            )
            if _sha256(content) != digest:
                raise LifecycleError("staged config extra changed before sealing")
            path.chmod(0o444)
        (config / "manifest.json").chmod(0o444)
        directories = [path for path in config.rglob("*") if path.is_dir()]
        for directory in sorted(
            directories, key=lambda path: len(path.parts), reverse=True
        ):
            directory.chmod(0o555)
        config.chmod(0o555)
    except LifecycleError:
        raise
    except OSError as exc:
        raise LifecycleError(f"could not seal composed runtime config: {exc}") from exc


def _copy_distribution(
    distribution: VerifiedDistribution, destination: Path, *, immutable: bool
) -> None:
    try:
        destination.mkdir(parents=True)
        for entry in distribution.entries:
            source = distribution.root.joinpath(*entry.relative.parts)
            target = destination.joinpath(*entry.relative.parts)
            _write_verified_file(source, target, entry)
        manifest_path = destination / DISTRIBUTION_MANIFEST
        with manifest_path.open("xb") as output:
            output.write(distribution.manifest_bytes)
        manifest_path.chmod(0o644)
        if immutable:
            for entry in distribution.entries:
                destination.joinpath(*entry.relative.parts).chmod(entry.mode & ~0o222)
            manifest_path.chmod(0o444)
            directories = [path for path in destination.rglob("*") if path.is_dir()]
            for directory in sorted(
                directories, key=lambda path: len(path.parts), reverse=True
            ):
                directory.chmod(0o555)
            destination.chmod(0o555)
    except LifecycleError:
        raise
    except OSError as exc:
        raise LifecycleError(
            f"could not stage distribution at {destination}: {exc}"
        ) from exc


def _make_tree_removable(root: Path) -> None:
    if not root.exists() or root.is_symlink():
        return
    for current, directories, files in os.walk(root, topdown=False, followlinks=False):
        current_path = Path(current)
        for name in files:
            child = current_path / name
            try:
                if not child.is_symlink():
                    child.chmod(0o600)
            except OSError:
                pass
        for name in directories:
            child = current_path / name
            if not child.is_symlink():
                try:
                    child.chmod(0o700)
                except OSError:
                    pass
    try:
        root.chmod(0o700)
    except OSError:
        pass


def _remove_private_tree(root: Path) -> None:
    _make_tree_removable(root)
    try:
        shutil.rmtree(root)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise LifecycleError(f"could not remove private staging directory {root}: {exc}") from exc


@contextmanager
def _lifecycle_lock(home: Path, *, create: bool = False) -> Iterator[None]:
    exists = _inspect_owned_directory(home, label="OpenCode lifecycle home")
    if not exists:
        if not create:
            raise LifecycleError(f"existing lifecycle home is required: {home}")
        try:
            home.mkdir(parents=True, mode=0o700)
        except OSError as exc:
            raise LifecycleError(f"could not create OpenCode lifecycle home {home}: {exc}") from exc
        if not _inspect_owned_directory(home, label="OpenCode lifecycle home"):
            raise LifecycleError(f"could not create OpenCode lifecycle home: {home}")
    home_mode = stat.S_IMODE(home.stat().st_mode)
    if home_mode != 0o700:
        raise LifecycleError(
            f"OpenCode lifecycle home must have mode 0700: {home}"
        )
    lock_path = home / ".lock"
    flags = os.O_RDWR | (os.O_CREAT if create else 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(lock_path, flags, SAFE_STATE_MODE)
    except OSError as exc:
        raise LifecycleError(f"could not open lifecycle lock {lock_path}: {exc}") from exc
    try:
        lock_stat = os.fstat(descriptor)
        if not stat.S_ISREG(lock_stat.st_mode):
            raise LifecycleError(f"lifecycle lock is not a regular file: {lock_path}")
        if hasattr(os, "geteuid") and lock_stat.st_uid != os.geteuid():
            raise LifecycleError(f"lifecycle lock is not owned by this user: {lock_path}")
        lock_mode = stat.S_IMODE(lock_stat.st_mode)
        if lock_mode != SAFE_STATE_MODE:
            raise LifecycleError(f"lifecycle lock must have mode 0600: {lock_path}")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _validate_release_id(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not RELEASE_ID_PATTERN.fullmatch(value):
        raise LifecycleError(f"state field {field!r} is not a valid release ID")
    return value


def _load_state(home: Path, *, required: bool) -> dict[str, object] | None:
    path = home / "state.json"
    try:
        content, path_stat = _regular_file(path, label="lifecycle state")
    except LifecycleError:
        if not path.exists() and not path.is_symlink() and not required:
            return None
        raise
    if stat.S_IMODE(path_stat.st_mode) != SAFE_STATE_MODE:
        raise LifecycleError(f"lifecycle state must have mode 0600: {path}")
    if hasattr(os, "geteuid") and path_stat.st_uid != os.geteuid():
        raise LifecycleError(f"lifecycle state is not owned by this user: {path}")
    value = _parse_json_object(content, label=f"lifecycle state {path}")
    if set(value) != {"schemaVersion", "active", "previous"}:
        raise LifecycleError(f"lifecycle state has unexpected fields: {path}")
    if (
        type(value.get("schemaVersion")) is not int
        or value["schemaVersion"] != STATE_SCHEMA_VERSION
    ):
        raise LifecycleError(f"lifecycle state has an unsupported schema: {path}")
    active = _validate_release_id(value.get("active"), field="active")
    previous_value = value.get("previous")
    previous = (
        None
        if previous_value is None
        else _validate_release_id(previous_value, field="previous")
    )
    return {"schemaVersion": STATE_SCHEMA_VERSION, "active": active, "previous": previous}


def _atomic_write_state(home: Path, state: Mapping[str, object]) -> None:
    path = home / "state.json"
    if path.is_symlink():
        raise LifecycleError(f"refusing to replace symlinked lifecycle state: {path}")
    content = (json.dumps(state, sort_keys=True, separators=(",", ":")) + "\n").encode()
    descriptor, temporary_name = tempfile.mkstemp(prefix=".state-", dir=home)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, SAFE_STATE_MODE)
        with os.fdopen(descriptor, "wb", closefd=True) as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        path.chmod(SAFE_STATE_MODE)
        _fsync_directory(home)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise LifecycleError(f"could not update lifecycle state {path}: {exc}") from exc


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    try:
        descriptor = os.open(path, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise LifecycleError(f"could not durably sync directory {path}: {exc}") from exc


def _release_distribution(
    home: Path, release_id: str, *, require_current_contract: bool = True
) -> VerifiedDistribution:
    _validate_release_id(release_id, field="release")
    release_root = home / "releases" / release_id
    if release_root.is_symlink():
        raise LifecycleError(f"refusing to use symlinked release: {release_root}")
    distribution_root = release_root / "distribution"
    verified = verify_distribution(
        distribution_root,
        immutable=True,
        require_current_contract=require_current_contract,
    )
    if verified.release_id != release_id:
        raise LifecycleError(
            f"installed release directory {release_id} contains distribution manifest "
            f"{verified.release_id}"
        )
    return verified


def install(source: Path, home: Path) -> tuple[str, bool]:
    source = source.expanduser().absolute()
    resolved_source = _resolved(source)
    home = _resolved(home)
    if _paths_overlap(home, resolved_source):
        raise LifecycleError(
            "lifecycle home must not overlap the verified distribution source: "
            f"home={home}, source={resolved_source}"
        )
    project_root = _resolved(_project_root(os.environ))
    if _paths_overlap(home, project_root):
        raise LifecycleError(
            "lifecycle home must not overlap the current repository: "
            f"home={home}, repository={project_root}"
        )
    for ambient_root in _ambient_opencode_write_roots(os.environ):
        if _paths_overlap(home, ambient_root):
            raise LifecycleError(
                "lifecycle home is inside an ambient cplt/OpenCode write area: "
                f"{ambient_root}"
            )
    verified_source = verify_distribution(source, immutable=False)
    release_id = verified_source.release_id
    changed = False
    with _lifecycle_lock(home, create=True):
        releases = home / "releases"
        _ensure_owned_directory(releases, label="OpenCode releases directory")
        current = _load_state(home, required=False)
        if current is not None:
            _release_distribution(
                home,
                _validate_release_id(current["active"], field="active"),
                require_current_contract=False,
            )
        destination_root = releases / release_id
        if destination_root.exists() or destination_root.is_symlink():
            _release_distribution(home, release_id)
        else:
            stage_root = Path(tempfile.mkdtemp(prefix=".install-", dir=releases))
            published = False
            try:
                _copy_distribution(
                    verified_source, stage_root / "distribution", immutable=True
                )
                installed = verify_distribution(
                    stage_root / "distribution", immutable=True
                )
                if installed.release_id != release_id:  # pragma: no cover
                    raise LifecycleError("staged release ID changed during installation")
                # Keep the source directory owner-writable for the rename.
                # Darwin can reject renaming a 0555 directory even when its
                # parent is writable. The verified distribution below it is
                # already sealed; seal the release root immediately after the
                # atomic publication.
                os.replace(stage_root, destination_root)
                published = True
                destination_root.chmod(0o555)
                _fsync_directory(releases)
            except Exception as exc:
                cleanup_root = destination_root if published else stage_root
                if cleanup_root.exists():
                    _remove_private_tree(cleanup_root)
                if isinstance(exc, OSError):
                    raise LifecycleError(
                        f"could not publish installed release {release_id}: {exc}"
                    ) from exc
                raise
            changed = True

        if current is None:
            desired: dict[str, object] = {
                "schemaVersion": STATE_SCHEMA_VERSION,
                "active": release_id,
                "previous": None,
            }
        elif current["active"] == release_id:
            desired = current
        else:
            desired = {
                "schemaVersion": STATE_SCHEMA_VERSION,
                "active": release_id,
                "previous": current["active"],
            }
        if current != desired:
            _atomic_write_state(home, desired)
            changed = True
    return release_id, changed


def rollback(home: Path) -> str:
    home = _resolved(home)
    with _lifecycle_lock(home):
        state = _load_state(home, required=True)
        assert state is not None
        previous = state.get("previous")
        if not isinstance(previous, str):
            raise LifecycleError("no previous OpenCode release is available for rollback")
        active = _validate_release_id(state.get("active"), field="active")
        _release_distribution(home, active)
        _release_distribution(home, previous, require_current_contract=False)
        _atomic_write_state(
            home,
            {
                "schemaVersion": STATE_SCHEMA_VERSION,
                "active": previous,
                "previous": active,
            },
        )
        return previous


def _profile_object(path: Path) -> dict[str, Any]:
    content = _regular_file_bytes(
        path, label="runtime profile", max_bytes=MAX_JSON_BYTES
    )
    return _parse_json_object(content, label=f"runtime profile {path}")


def _validate_domain(value: object, *, label: str) -> str:
    if not isinstance(value, str):
        raise LifecycleError(f"{label} must be a bare domain")
    domain = value.strip().lower().rstrip(".")
    literal_candidate = (
        domain[1:-1]
        if domain.startswith("[") and domain.endswith("]")
        else domain
    )
    try:
        ipaddress.ip_address(literal_candidate)
    except ValueError:
        pass
    else:
        raise LifecycleError(f"{label} must be a hostname, not an IP literal: {value!r}")
    domain_parts = domain.split(".")
    if len(domain_parts) > 1 and all(part.isdecimal() for part in domain_parts):
        raise LifecycleError(f"{label} must be a hostname, not an IP literal: {value!r}")
    if domain == "localhost" or domain.endswith(".localhost"):
        raise LifecycleError(f"{label} must not be a localhost name: {value!r}")
    if (
        not domain
        or len(domain) > 253
        or "://" in domain
        or any(character in domain for character in "/:*@")
        or len(domain.split(".")) < 2
        or any(not DOMAIN_LABEL_PATTERN.fullmatch(part) for part in domain_parts)
    ):
        raise LifecycleError(
            f"{label} must be a bare domain without scheme, path, port or wildcard: "
            f"{value!r}"
        )
    return domain


def load_profile(
    profile_id: str, *, profile_root: Path = PROFILE_ROOT
) -> RuntimeProfile:
    if not re.fullmatch(r"[a-z][a-z0-9-]*", profile_id):
        raise LifecycleError(f"invalid runtime profile ID: {profile_id!r}")
    if profile_id not in PROFILE_SHAPES:
        raise LifecycleError(f"unsupported runtime profile ID: {profile_id!r}")
    path = profile_root / f"{profile_id}.json"
    value = _profile_object(path)
    if (
        type(value.get("schemaVersion")) is not int
        or value["schemaVersion"] != PROFILE_SCHEMA_VERSION
    ):
        raise LifecycleError(f"runtime profile {profile_id!r} has unsupported schema")
    if value.get("id") != profile_id:
        raise LifecycleError(f"runtime profile filename and id differ: {path}")
    description = value.get("description")
    cplt_policy = value.get("cpltPolicy")
    local_ports = value.get("localPorts")
    provider_domains = value.get("providerDomains")
    environment = value.get("environment")
    if not isinstance(description, str) or not description.strip():
        raise LifecycleError(f"runtime profile {profile_id!r} needs a description")
    observed_shape = (cplt_policy, local_ports, provider_domains)
    if observed_shape != PROFILE_SHAPES[profile_id]:
        raise LifecycleError(
            f"runtime profile {profile_id!r} has an invalid policy shape"
        )
    if not isinstance(environment, dict) or any(
        not isinstance(key, str) or not isinstance(item, str)
        for key, item in environment.items()
    ):
        raise LifecycleError(f"runtime profile {profile_id!r} environment is invalid")
    for name in environment:
        if not ENVIRONMENT_NAME_PATTERN.fullmatch(name) or not name.startswith(
            "OPENCODE_"
        ):
            raise LifecycleError(
                f"runtime profile {profile_id!r} has unsafe environment name {name!r}"
            )

    cplt_release = value.get("cpltRelease")
    allowed_domain = value.get("allowedDomain")
    raw_blocked = value.get("blockedDomains", [])
    common_fields = {
        "schemaVersion",
        "id",
        "description",
        "cpltPolicy",
        "cpltRelease",
        "localPorts",
        "providerDomains",
        "environment",
    }
    if cplt_release != SUPPORTED_CPLT_RELEASE:
        raise LifecycleError(
            f"runtime profile {profile_id!r} must pin cplt {SUPPORTED_CPLT_RELEASE}"
        )
    expected_environment = (
        LOCAL_ONLY_ENVIRONMENT
        if profile_id == "local-only"
        else BASE_PROFILE_ENVIRONMENT
    )
    if environment != expected_environment:
        raise LifecycleError(
            f"runtime profile {profile_id!r} has an invalid immutable environment overlay"
        )
    if profile_id == "local-only":
        if set(value) != common_fields | {"allowedDomain", "blockedDomains"}:
            raise LifecycleError("local-only profile has unexpected or missing fields")
        allowed_domain = _validate_domain(
            allowed_domain, label="local-only sentinel allowed domain"
        )
        if not isinstance(raw_blocked, list) or not raw_blocked:
            raise LifecycleError("local-only profile must block cplt's built-in domains")
        blocked = tuple(
            _validate_domain(domain, label="local-only blocked domain")
            for domain in raw_blocked
        )
        if allowed_domain != LOCAL_ONLY_ALLOWED_DOMAIN:
            raise LifecycleError(
                f"local-only allowed domain must be {LOCAL_ONLY_ALLOWED_DOMAIN!r}"
            )
        if len(blocked) != len(LOCAL_ONLY_BLOCKED_DOMAINS) or set(blocked) != (
            LOCAL_ONLY_BLOCKED_DOMAINS
        ):
            raise LifecycleError(
                "local-only blocked domains must exactly match the audited cplt defaults"
            )
    else:
        if set(value) != common_fields:
            raise LifecycleError(
                f"strict runtime profile {profile_id!r} has unexpected or missing fields"
            )
        if allowed_domain is not None or raw_blocked:
            raise LifecycleError(
                f"strict runtime profile {profile_id!r} has local-only fields"
            )
        blocked = ()
        allowed_domain = None

    return RuntimeProfile(
        id=profile_id,
        description=description,
        cplt_policy=cplt_policy,
        local_ports=local_ports,
        provider_domains=provider_domains,
        environment=dict(environment),
        cplt_release=cplt_release,
        allowed_domain=allowed_domain,
        blocked_domains=blocked,
    )


def _comma_values(value: str | None) -> list[str]:
    if value is None or not value.strip():
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _is_forbidden_pass_environment(name: str) -> bool:
    """Protect cplt's hardening and every pre-sandbox interpreter/loader."""

    normalized = name.upper()
    return (
        normalized in FORBIDDEN_LOADER_ENVIRONMENT
        or normalized in FORBIDDEN_CPLT_HARDENING_ENVIRONMENT
        or normalized in {"GH_TOKEN", "GITHUB_TOKEN"}
        or normalized.startswith("COPILOT_")
        or normalized.startswith("DYLD_")
        or normalized.startswith("BUN_")
        or normalized.startswith("CPLT_")
        or normalized.startswith("__CPLT_")
        or normalized.startswith("GIT_CONFIG_KEY_")
        or normalized.startswith("GIT_CONFIG_VALUE_")
        or (
            normalized.startswith(("CORECLR_", "COR_"))
            and "PROFIL" in normalized
        )
    )


def _resolve_runtime_inputs(
    profile_id: str,
    local_ports: Sequence[int],
    provider_domains: Sequence[str],
    provider_ports: Sequence[int],
    private_provider_domains: Sequence[str],
    pass_environment: Sequence[str],
    auth_providers: Sequence[str],
    provider_ids: Sequence[str],
    provider_base_urls: Sequence[str],
    provider_models: Sequence[str],
    environment: Mapping[str, str],
    *,
    profile_root: Path = PROFILE_ROOT,
) -> RuntimeInputs:
    profile = load_profile(profile_id, profile_root=profile_root)
    raw_ports: list[int] = list(local_ports)
    for value in _comma_values(environment.get("GRILLMESTER_OPENCODE_LOCAL_PORTS")):
        try:
            raw_ports.append(int(value))
        except ValueError as exc:
            raise LifecycleError(f"local port is not an integer: {value!r}") from exc
    ports = tuple(sorted(set(raw_ports)))
    if any(port < 1 or port > 65535 for port in ports):
        raise LifecycleError("local ports must be in the range 1..65535")
    if profile.local_ports == "required" and not ports:
        raise LifecycleError(f"profile {profile.id!r} requires at least one local port")
    if profile.local_ports == "forbidden" and ports:
        raise LifecycleError(f"profile {profile.id!r} forbids a local port")

    raw_domains = list(provider_domains) + _comma_values(
        environment.get("GRILLMESTER_OPENCODE_PROVIDER_DOMAINS")
    )
    domains = tuple(
        sorted(
            {
                _validate_domain(domain, label="provider domain")
                for domain in raw_domains
            }
        )
    )
    if profile.provider_domains == "required" and not domains:
        raise LifecycleError(
            f"profile {profile.id!r} requires at least one provider domain"
        )
    if profile.provider_domains == "forbidden" and domains:
        raise LifecycleError(f"profile {profile.id!r} forbids a provider domain")

    raw_provider_ports: list[int] = list(provider_ports)
    for value in _comma_values(
        environment.get("GRILLMESTER_OPENCODE_PROVIDER_PORTS")
    ):
        try:
            raw_provider_ports.append(int(value))
        except ValueError as exc:
            raise LifecycleError(
                f"provider port is not an integer: {value!r}"
            ) from exc
    cloud_ports = tuple(sorted(set(raw_provider_ports)))
    if any(port < 1 or port > 65535 for port in cloud_ports):
        raise LifecycleError("provider ports must be in the range 1..65535")
    if profile.provider_domains == "forbidden" and cloud_ports:
        raise LifecycleError(f"profile {profile.id!r} forbids a provider port")
    if any(port != 443 for port in cloud_ports):
        raise LifecycleError(
            "managed provider endpoints support HTTPS port 443 only; pinned cplt's "
            "--allow-port would grant direct egress to every host on that port"
        )
    # HTTPS 443 is already carried by the forced domain-filtering proxy. Never
    # translate even a redundant 443 into cplt --allow-port, which is a kernel
    # any-host exception rather than a provider-scoped port.
    cloud_ports = ()

    raw_private_domains = list(private_provider_domains) + _comma_values(
        environment.get("GRILLMESTER_OPENCODE_PRIVATE_PROVIDER_DOMAINS")
    )
    private_domains = tuple(
        sorted(
            {
                _validate_domain(domain, label="private provider domain")
                for domain in raw_private_domains
            }
        )
    )
    if any(domain not in domains for domain in private_domains):
        raise LifecycleError(
            "every private provider domain must also be an exact --provider-domain"
        )
    if profile.id == "cloud-open-weight" and private_domains:
        raise LifecycleError(
            "profile 'cloud-open-weight' permits public provider hostnames only; "
            "use 'hybrid' for an explicitly private/internal provider domain"
        )

    raw_auth_providers = list(auth_providers) + _comma_values(
        environment.get("GRILLMESTER_OPENCODE_AUTH_PROVIDERS")
    )
    selected_auth_providers: list[str] = []
    for provider_id in raw_auth_providers:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", provider_id):
            raise LifecycleError(f"invalid OpenCode auth provider ID: {provider_id!r}")
        if provider_id not in selected_auth_providers:
            selected_auth_providers.append(provider_id)
    if profile.cplt_policy == "local-only" and selected_auth_providers:
        raise LifecycleError(
            "profile 'local-only' forbids ambient auth.json credentials; use an "
            "explicit provider credential environment variable when required"
        )

    raw_provider_ids = list(provider_ids) + _comma_values(
        environment.get("GRILLMESTER_OPENCODE_PROVIDER_IDS")
    )
    selected_provider_ids: list[str] = []
    for provider_id in raw_provider_ids:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", provider_id):
            raise LifecycleError(f"invalid OpenCode provider ID: {provider_id!r}")
        if provider_id not in selected_provider_ids:
            selected_provider_ids.append(provider_id)
    unselected_auth = sorted(set(selected_auth_providers) - set(selected_provider_ids))
    if unselected_auth:
        raise LifecycleError(
            "auth providers must also be selected with --provider-id: "
            + ", ".join(unselected_auth)
        )

    raw_base_urls = list(provider_base_urls) + _comma_values(
        environment.get("GRILLMESTER_OPENCODE_PROVIDER_BASE_URLS")
    )
    selected_base_urls: dict[str, str] = {}
    for assignment in raw_base_urls:
        provider_id, separator, base_url = assignment.partition("=")
        if (
            not separator
            or provider_id not in selected_provider_ids
            or not base_url
            or provider_id in selected_base_urls
        ):
            raise LifecycleError(
                "provider base URLs must be unique ID=URL assignments for exact "
                "--provider-id selections"
            )
        selected_base_urls[provider_id] = base_url
    if set(selected_base_urls) != set(selected_provider_ids):
        raise LifecycleError(
            "every --provider-id requires exactly one --provider-base-url ID=URL"
        )

    raw_models = list(provider_models) + _comma_values(
        environment.get("GRILLMESTER_OPENCODE_PROVIDER_MODELS")
    )
    selected_models: list[tuple[str, str]] = []
    for reference in raw_models:
        provider_id, separator, model_id = reference.partition("/")
        if (
            not separator
            or provider_id not in selected_provider_ids
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}", model_id)
        ):
            raise LifecycleError(
                "provider models must be PROVIDER/MODEL references for exact "
                "--provider-id selections"
            )
        pair = (provider_id, model_id)
        if pair not in selected_models:
            selected_models.append(pair)
    providers_with_models = {provider_id for provider_id, _model_id in selected_models}
    if providers_with_models != set(selected_provider_ids):
        raise LifecycleError(
            "every --provider-id requires at least one --provider-model PROVIDER/MODEL"
        )

    raw_environment = list(pass_environment) + _comma_values(
        environment.get("GRILLMESTER_OPENCODE_PASS_ENV")
    )
    passed: list[str] = []
    for name in raw_environment:
        if not ENVIRONMENT_NAME_PATTERN.fullmatch(name):
            raise LifecycleError(f"invalid environment variable name: {name!r}")
        if (
            name in CONTROL_ENVIRONMENT_NAMES
            or name.startswith("GRILLMESTER_")
            or name.startswith("OPENCODE_")
            or _is_forbidden_pass_environment(name)
        ):
            raise LifecycleError(
                f"environment variable is controlled by the launcher and cannot be passed: {name}"
            )
        if name in profile.environment:
            raise LifecycleError(
                f"environment variable is managed by profile {profile.id!r}: {name}"
            )
        if name not in environment:
            raise LifecycleError(f"environment variable is not set: {name}")
        if name not in passed:
            passed.append(name)
    return RuntimeInputs(
        profile,
        ports,
        domains,
        cloud_ports,
        private_domains,
        tuple(passed),
        tuple(selected_auth_providers),
        tuple(selected_provider_ids),
        tuple(sorted(selected_base_urls.items())),
        tuple(selected_models),
    )


def _write_policy_file(path: Path, values: Sequence[str]) -> None:
    content = "".join(f"{value}\n" for value in values)
    try:
        path.write_text(content, encoding="utf-8")
        path.chmod(0o400)
    except OSError as exc:
        raise LifecycleError(f"could not write ephemeral cplt policy {path}: {exc}") from exc


def _resolve_executable(
    executable: str, *, label: str, environment: Mapping[str, str]
) -> str:
    if not executable:
        raise LifecycleError(f"{label} executable must not be empty")
    if os.sep in executable or (os.altsep is not None and os.altsep in executable):
        candidate = Path(executable).expanduser()
    else:
        found = shutil.which(executable, path=environment.get("PATH"))
        if found is None:
            raise LifecycleError(f"could not find {label} executable {executable!r} on PATH")
        candidate = Path(found)
    try:
        resolved = candidate.absolute().resolve(strict=True)
        observed = resolved.stat()
    except OSError as exc:
        raise LifecycleError(
            f"could not resolve {label} executable {executable!r}: {exc}"
        ) from exc
    if not stat.S_ISREG(observed.st_mode) or not os.access(resolved, os.X_OK):
        raise LifecycleError(
            f"{label} executable is not an executable regular file: {resolved}"
        )
    return str(resolved)


def _host_platform_tuple() -> tuple[str, str]:
    if sys.platform == "darwin":
        operating_system = "darwin"
    elif sys.platform.startswith("linux"):
        operating_system = "linux"
    else:
        raise LifecycleError(
            f"checksum-pinned cplt is unsupported on platform "
            f"{platform.system() or sys.platform!r}"
        )
    machine = platform.machine().strip().lower()
    if machine in {"amd64", "x64", "x86_64"}:
        architecture = "x86_64"
    elif machine in {"aarch64", "arm64"}:
        architecture = "arm64" if operating_system == "darwin" else "aarch64"
    else:
        raise LifecycleError(
            f"checksum-pinned clients are unsupported on architecture "
            f"{platform.machine() or '<unknown>'!r}"
        )
    return operating_system, architecture


def _expected_cplt_binary_digests() -> frozenset[str]:
    platform_tuple = _host_platform_tuple()
    digest = PINNED_CPLT_BINARY_SHA256.get(platform_tuple)
    if digest is None:
        raise LifecycleError(
            "checksum-pinned cplt has no release asset for "
            + "/".join(platform_tuple)
        )
    return frozenset({digest})


def _require_managed_cplt_libc() -> None:
    """Fail closed when the pinned native cplt has no compatible Linux asset."""

    operating_system, _architecture = _host_platform_tuple()
    if operating_system != "linux":
        return
    libc_name, _libc_version = platform.libc_ver()
    if libc_name.strip().lower() not in {"glibc", "gnu libc"}:
        raise LifecycleError(
            "managed cplt on Linux requires a glibc host; the pinned release has "
            "no musl asset. Use native unmanaged OpenCode on musl, or run the "
            "managed profile on a supported glibc host"
        )


def _expected_opencode_binary_digests() -> frozenset[str]:
    operating_system, architecture = _host_platform_tuple()
    digests = frozenset(
        digest
        for (system, machine, _variant), digest in PINNED_OPENCODE_BINARY_SHA256.items()
        if system == operating_system and machine == architecture
    )
    if not digests:
        raise LifecycleError(
            "checksum-pinned OpenCode has no release asset for "
            f"{operating_system}/{architecture}"
        )
    return digests


def _stage_private_executable(
    source: Path,
    session: Path,
    *,
    name: str,
    label: str,
    max_bytes: int,
    expected_digests: frozenset[str] | None = None,
) -> str:
    """Stage one bounded executable and recheck the private copy by digest."""

    content, observed = _regular_file(source, label=label, max_bytes=max_bytes)
    if observed.st_mode & 0o111 == 0:
        raise LifecycleError(f"{label} lost its executable mode before staging: {source}")
    observed_digest = _sha256(content)
    if expected_digests is not None and observed_digest not in expected_digests:
        operating_system, architecture = _host_platform_tuple()
        raise LifecycleError(
            f"{label} checksum does not match a pinned upstream release asset for "
            f"{operating_system}/{architecture}"
        )
    trusted_directory = session / "trusted-bin"
    destination = trusted_directory / name
    try:
        _ensure_owned_directory(
            trusted_directory, label="private executable staging directory"
        )
        with destination.open("xb") as output:
            output.write(content)
        destination.chmod(0o500)
    except OSError as exc:
        raise LifecycleError(f"could not stage {label}: {exc}") from exc
    staged = _regular_file_bytes(
        destination, label=f"staged {label}", max_bytes=max_bytes
    )
    if _sha256(staged) != observed_digest:  # pragma: no cover - fresh private directory
        raise LifecycleError(f"{label} changed while it was being staged")
    return str(destination)


def _stage_pinned_cplt_binary(source: Path, session: Path) -> str:
    """Verify cplt before execution and run an immutable private byte-for-byte copy."""

    return _stage_private_executable(
        source,
        session,
        name="cplt",
        label="cplt executable",
        max_bytes=MAX_FILE_BYTES,
        expected_digests=_expected_cplt_binary_digests(),
    )


def _stage_opencode_binary(source: Path, session: Path) -> str:
    """Authenticate and stage official OpenCode bytes without executing source."""

    return _stage_private_executable(
        source,
        session,
        name="opencode",
        label="OpenCode executable",
        max_bytes=MAX_EXECUTABLE_BYTES,
        expected_digests=_expected_opencode_binary_digests(),
    )


def _seal_trusted_executable_directory(directory: Path) -> None:
    """Make the complete executable set non-writable before the first exec."""

    if not _inspect_owned_directory(directory, label="trusted executable directory"):
        raise LifecycleError(f"missing trusted executable directory: {directory}")
    try:
        entries = sorted(path.name for path in directory.iterdir())
    except OSError as exc:
        raise LifecycleError(f"could not inspect trusted executable directory: {exc}") from exc
    if entries != ["cplt", "opencode"]:
        raise LifecycleError(
            "trusted executable directory must contain exactly cplt and opencode"
        )
    try:
        directory.chmod(0o500)
    except OSError as exc:
        raise LifecycleError(f"could not seal trusted executable directory: {exc}") from exc


def _recheck_staged_executable(
    path: Path,
    *,
    label: str,
    max_bytes: int,
    expected_digests: frozenset[str],
) -> None:
    """Re-stat and re-hash one sealed executable immediately before execution."""

    directory = path.parent
    try:
        directory_stat = directory.lstat()
    except OSError as exc:
        raise LifecycleError(f"could not inspect sealed {label} directory: {exc}") from exc
    if (
        not stat.S_ISDIR(directory_stat.st_mode)
        or stat.S_IMODE(directory_stat.st_mode) != 0o500
        or (hasattr(os, "geteuid") and directory_stat.st_uid != os.geteuid())
    ):
        raise LifecycleError(f"sealed {label} directory lost its 0500 ownership contract")
    content, observed = _regular_file(path, label=f"staged {label}", max_bytes=max_bytes)
    if (
        stat.S_IMODE(observed.st_mode) != 0o500
        or (hasattr(os, "geteuid") and observed.st_uid != os.geteuid())
        or _sha256(content) not in expected_digests
    ):
        raise LifecycleError(f"staged {label} changed after authenticated staging")


def _recheck_managed_command_executables(
    command: Sequence[str], environment: Mapping[str, str]
) -> None:
    if not command:
        raise LifecycleError("managed cplt command is empty")
    cplt_path = Path(command[0])
    path_entries = environment.get("PATH", "").split(os.pathsep)
    if not path_entries:
        raise LifecycleError("managed cplt command has no trusted PATH")
    opencode_path = Path(path_entries[0]) / "opencode"
    if not _same_path(cplt_path.parent, opencode_path.parent):
        raise LifecycleError("managed cplt and OpenCode are not in one sealed directory")
    _recheck_staged_executable(
        cplt_path,
        label="cplt executable",
        max_bytes=MAX_FILE_BYTES,
        expected_digests=_expected_cplt_binary_digests(),
    )
    _recheck_staged_executable(
        opencode_path,
        label="OpenCode executable",
        max_bytes=MAX_EXECUTABLE_BYTES,
        expected_digests=_expected_opencode_binary_digests(),
    )


def _check_exact_client_version(
    executable: str,
    *,
    label: str,
    expected_output: str,
    environment: Mapping[str, str],
) -> None:
    version_environment = {
        key: environment[key]
        for key in (
            "HOME",
            "LANG",
            "LC_ALL",
            "PATH",
            "SYSTEMROOT",
            "TMPDIR",
            "WINDIR",
        )
        if key in environment
    }
    version_environment.setdefault("PATH", os.defpath)
    returncode, stdout, stderr = _bounded_subprocess_output(
        [executable, "--version"],
        environment=version_environment,
        label=f"{label} version check",
    )
    try:
        observed_stdout = stdout.decode("utf-8").strip()
        observed_stderr = stderr.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise LifecycleError(f"{label} version output is not UTF-8") from exc
    if (
        returncode != 0
        or observed_stdout != expected_output
        or observed_stderr
    ):
        observed = " | ".join(
            value for value in (observed_stdout, observed_stderr) if value
        )
        raise LifecycleError(
            f"{label} must be exactly {expected_output!r}; observed "
            f"{observed or '<no version output>'!r}"
        )


def _parse_cplt_toml(path: Path, *, label: str) -> Mapping[str, Any] | None:
    if not path.exists() and not path.is_symlink():
        return None
    content = _regular_file_bytes(path, label=label, max_bytes=MAX_JSON_BYTES)
    try:
        value = tomllib.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise LifecycleError(f"cannot validate local-only against {label} {path}: {exc}") from exc
    if not isinstance(value, dict):  # pragma: no cover - tomllib always returns dict
        raise LifecycleError(f"{label} is not a TOML object: {path}")
    return value


def _nested_value(value: Mapping[str, Any], *keys: str) -> object:
    current: object = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _project_root(environment: Mapping[str, str]) -> Path:
    """Find the repository root without consulting caller-controlled Git state.

    ``GIT_DIR``, ``GIT_WORK_TREE`` and Git configuration environment variables can
    make ``git rev-parse`` report a repository unrelated to the process working
    directory.  The managed OpenCode checks must derive their scope from the same
    directory cplt receives, so inspect only the physical ancestor chain.  A
    worktree's regular ``.git`` file is a root marker; its contents are deliberately
    not parsed or trusted.

    ``environment`` remains in the signature for call-site compatibility.  It is
    intentionally ignored.
    """

    del environment
    current = _resolved(Path.cwd())
    for candidate in (current, *current.parents):
        marker = candidate / ".git"
        try:
            observed = marker.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise LifecycleError(
                f"could not inspect repository marker {marker}: {exc}"
            ) from exc
        if stat.S_ISLNK(observed.st_mode):
            raise LifecycleError(f"refusing symlinked repository marker: {marker}")
        if stat.S_ISDIR(observed.st_mode) or stat.S_ISREG(observed.st_mode):
            return candidate
        raise LifecycleError(
            f"repository marker must be a directory or regular file: {marker}"
        )
    return current


def _strip_jsonc(content: str, *, label: str) -> str:
    """Remove JSONC comments and trailing commas without touching strings."""

    output: list[str] = []
    index = 0
    in_string = False
    escaped = False
    while index < len(content):
        character = content[index]
        following = content[index + 1] if index + 1 < len(content) else ""
        if in_string:
            output.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            index += 1
            continue
        if character == '"':
            in_string = True
            output.append(character)
            index += 1
            continue
        if character == "/" and following == "/":
            output.extend((" ", " "))
            index += 2
            while index < len(content) and content[index] not in "\r\n":
                output.append(" ")
                index += 1
            continue
        if character == "/" and following == "*":
            output.extend((" ", " "))
            index += 2
            closed = False
            while index < len(content):
                current = content[index]
                next_character = content[index + 1] if index + 1 < len(content) else ""
                if current == "*" and next_character == "/":
                    output.extend((" ", " "))
                    index += 2
                    closed = True
                    break
                output.append(current if current in "\r\n" else " ")
                index += 1
            if not closed:
                raise LifecycleError(f"unterminated block comment in {label}")
            continue
        output.append(character)
        index += 1
    if in_string:
        raise LifecycleError(f"unterminated string in {label}")

    stripped = output
    index = 0
    in_string = False
    escaped = False
    while index < len(stripped):
        character = stripped[index]
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            index += 1
            continue
        if character == '"':
            in_string = True
            index += 1
            continue
        if character == ",":
            lookahead = index + 1
            while lookahead < len(stripped) and stripped[lookahead].isspace():
                lookahead += 1
            if lookahead < len(stripped) and stripped[lookahead] in "}]":
                stripped[index] = " "
        index += 1
    return "".join(stripped)


def _parse_opencode_jsonc(path: Path) -> tuple[dict[str, Any], bytes]:
    content = _regular_file_bytes(
        path, label="OpenCode config", max_bytes=MAX_JSON_BYTES
    )
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LifecycleError(f"OpenCode config is not UTF-8: {path}") from exc
    cleaned = _strip_jsonc(text, label=str(path))
    try:
        value = json.loads(
            cleaned,
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_nonstandard_json_constant,
        )
    except json.JSONDecodeError as exc:
        raise LifecycleError(
            f"OpenCode config is not valid JSONC at {path}:{exc.lineno}:{exc.colno}"
        ) from exc
    except RecursionError as exc:
        raise LifecycleError(f"OpenCode config is too deeply nested: {path}") from exc
    if not isinstance(value, dict):
        raise LifecycleError(f"OpenCode config must be an object: {path}")
    _require_bounded_json_depth(value, label="OpenCode config")
    return value, content


def _reject_declared_opencode_extensions(
    config: Mapping[str, Any], *, label: str
) -> None:
    plugins = config.get("plugin")
    if plugins not in (None, []):
        raise LifecycleError(
            f"managed Grillmester sessions forbid declared OpenCode plugins in {label}"
        )
    mcp = config.get("mcp")
    if mcp not in (None, {}):
        if not isinstance(mcp, dict):
            raise LifecycleError(f"OpenCode mcp config must be an object in {label}")
        enabled: list[str] = []
        for name, entry in mcp.items():
            if not isinstance(name, str) or not name or not isinstance(entry, dict):
                raise LifecycleError(f"OpenCode mcp entry is invalid in {label}")
            if entry.get("enabled") is not False:
                enabled.append(name)
        if enabled:
            raise LifecycleError(
                "managed Grillmester sessions forbid enabled OpenCode MCP servers "
                f"in {label}"
            )

    skills = config.get("skills")
    if skills not in (None, {}):
        if not isinstance(skills, dict):
            raise LifecycleError(f"OpenCode skills config must be an object in {label}")
        for field in ("paths", "urls"):
            if skills.get(field) not in (None, []):
                raise LifecycleError(
                    f"managed Grillmester sessions forbid OpenCode skills.{field} "
                    f"in {label}"
                )

    if config.get("instructions") not in (None, []):
        raise LifecycleError(
            f"managed Grillmester sessions forbid custom OpenCode instructions in {label}"
        )
    if config.get("shell") not in (None, ""):
        raise LifecycleError(
            f"managed Grillmester sessions forbid a custom OpenCode shell in {label}"
        )
    for field in ("references", "reference"):
        if config.get(field) not in (None, {}):
            raise LifecycleError(
                f"managed Grillmester sessions forbid OpenCode {field} in {label}"
            )
    server = config.get("server")
    if server not in (None, {}):
        if not isinstance(server, dict):
            raise LifecycleError(f"OpenCode server must be an object in {label}")
        if server.get("hostname") not in (None, "127.0.0.1", "localhost"):
            raise LifecycleError(
                f"managed Grillmester sessions require a loopback server in {label}"
            )
        if server.get("mdns") not in (None, False) or server.get("mdnsDomain") is not None:
            raise LifecycleError(
                f"managed Grillmester sessions forbid OpenCode mDNS in {label}"
            )
        if server.get("cors") not in (None, []):
            raise LifecycleError(
                f"managed Grillmester sessions forbid OpenCode CORS in {label}"
            )
    experimental = config.get("experimental")
    if experimental not in (None, {}):
        if not isinstance(experimental, dict):
            raise LifecycleError(
                f"OpenCode experimental config must be an object in {label}"
            )
        if experimental.get("openTelemetry") is True:
            raise LifecycleError(
                f"managed Grillmester sessions forbid OpenCode telemetry in {label}"
            )

    _reject_unsafe_provider_npm(config.get("provider"), label=f"{label} provider")
    _reject_executable_opencode_commands(
        config.get("lsp"), label=f"{label} lsp"
    )
    _reject_executable_opencode_commands(
        config.get("formatter"), label=f"{label} formatter"
    )


def _reject_unsafe_provider_npm(value: object, *, label: str) -> None:
    if value in (None, {}):
        return
    if not isinstance(value, dict):
        raise LifecycleError(f"OpenCode {label} must be an object")

    def check_npm(npm: object) -> None:
        if npm is not None and npm != SAFE_PROVIDER_NPM:
            raise LifecycleError(
                "OpenCode provider SDK must be omitted or exactly "
                f"{SAFE_PROVIDER_NPM!r} in a managed Grillmester session"
            )

    for provider_id, provider in value.items():
        if not isinstance(provider_id, str) or not provider_id or not isinstance(provider, dict):
            raise LifecycleError(f"OpenCode {label} contains an invalid provider")
        provider_npm = provider.get("npm")
        check_npm(provider_npm)
        models = provider.get("models")
        if models in (None, {}):
            continue
        if not isinstance(models, dict):
            raise LifecycleError(f"OpenCode {label} models must be an object")
        for model_id, model in models.items():
            if not isinstance(model_id, str) or not model_id or not isinstance(model, dict):
                raise LifecycleError(
                    f"OpenCode {label} models contain an invalid model"
                )
            model_provider = model.get("provider")
            if model_provider is None:
                model_provider = {}
            if not isinstance(model_provider, dict):
                raise LifecycleError(
                    f"OpenCode {label} model provider must be an object"
                )
            model_npm = model_provider.get("npm")
            check_npm(model_npm)
            if model_npm is None and provider_npm != SAFE_PROVIDER_NPM:
                raise LifecycleError(
                    f"OpenCode {label} model must resolve through exactly "
                    f"{SAFE_PROVIDER_NPM!r}"
                )


def _reject_executable_opencode_commands(value: object, *, label: str) -> None:
    if value in (None, False, {}):
        return
    if not isinstance(value, dict):
        raise LifecycleError(
            f"OpenCode {label} must be absent, false, or contain disabled-only entries"
        )
    for entry_id, entry in value.items():
        if (
            not isinstance(entry_id, str)
            or not entry_id
            or not isinstance(entry, dict)
            or entry.get("disabled") is not True
            or "command" in entry
        ):
            raise LifecycleError(
                f"OpenCode {label} contains an executable or non-disabled entry"
            )


def _managed_project_directories(project_root: Path) -> tuple[Path, ...]:
    project_root = _resolved(project_root)
    current = _resolved(Path.cwd())
    if not _is_within(current, project_root):
        raise LifecycleError(
            f"current directory {current} is outside OpenCode project root {project_root}"
        )
    project_directories: list[Path] = []
    cursor = current
    while True:
        project_directories.append(cursor)
        if _same_path(cursor, project_root):
            break
        parent = cursor.parent
        if parent == cursor:  # pragma: no cover - containment checked above
            raise LifecycleError("could not enumerate OpenCode project config roots")
        cursor = parent
    project_directories.reverse()
    return tuple(project_directories)


def _managed_opencode_search_roots(
    project_root: Path, environment: Mapping[str, str]
) -> tuple[tuple[Path, ...], tuple[Path, ...], tuple[Path, ...], tuple[Path, ...]]:
    """Return config files and auto-extension roots relevant to managed review."""

    project_directories = _managed_project_directories(project_root)

    account_home = _resolved(_account_home())
    raw_xdg = environment.get("XDG_CONFIG_HOME")
    xdg_config = _resolved(
        Path(raw_xdg).expanduser() if raw_xdg else account_home / ".config"
    )
    global_config = xdg_config / "opencode"
    opencode_directories = [
        global_config,
        account_home / ".opencode",
        *(directory / ".opencode" for directory in project_directories),
    ]
    config_files: list[Path] = [
        global_config / "config.json",
        global_config / "opencode.json",
        global_config / "opencode.jsonc",
        *(directory / name for directory in project_directories for name in ("opencode.json", "opencode.jsonc")),
        *(directory / name for directory in opencode_directories for name in ("opencode.json", "opencode.jsonc")),
    ]
    custom = environment.get("OPENCODE_CONFIG")
    if custom:
        config_files.append(_resolved(Path(custom).expanduser()))

    def unique(paths: Iterable[Path]) -> tuple[Path, ...]:
        result: list[Path] = []
        seen: set[tuple[str, ...]] = set()
        for path in paths:
            resolved = _resolved(path)
            key = _portable_absolute_path_key(resolved)
            if key not in seen:
                seen.add(key)
                result.append(resolved)
        return tuple(result)

    plugin_roots = unique(
        directory / plugin_name
        for directory in opencode_directories
        for plugin_name in ("plugin", "plugins")
    )
    tool_roots = unique(
        directory / tool_name
        for directory in opencode_directories
        for tool_name in ("tool", "tools")
    )
    skill_roots = unique(
        directory / skill_name
        for directory in opencode_directories
        for skill_name in ("skill", "skills")
    )
    return unique(config_files), plugin_roots, tool_roots, skill_roots


def _validate_restriction_only_permission(value: object, *, label: str) -> None:
    """Accept only project permission rules that cannot widen managed policy."""

    if value in (None, {}):
        return
    if not isinstance(value, dict):
        raise LifecycleError(f"{label} must be a restriction-only object")
    for key, rule in value.items():
        if not isinstance(key, str) or not key:
            raise LifecycleError(f"{label} has an invalid restriction-only key")
        if isinstance(rule, str):
            if rule not in {"ask", "deny"}:
                raise LifecycleError(f"{label} must be restriction-only")
            continue
        if (
            not isinstance(rule, dict)
            or not rule
            or any(
                not isinstance(pattern, str)
                or not pattern
                or action not in {"ask", "deny"}
                for pattern, action in rule.items()
            )
        ):
            raise LifecycleError(f"{label} must be restriction-only")


def _validate_restriction_only_tools(value: object, *, label: str) -> None:
    if value in (None, {}):
        return
    if (
        not isinstance(value, dict)
        or any(
            not isinstance(tool, str) or not tool or enabled is not False
            for tool, enabled in value.items()
        )
    ):
        raise LifecycleError(f"{label} must be restriction-only disabled tools")


def _validate_restriction_only_project_config(
    config: Mapping[str, Any], *, label: str
) -> None:
    """Constrain project config that pinned OpenCode core V2 still discovers."""

    unsupported = sorted(set(config) - {"$schema", "permission", "tools", "agent"})
    if unsupported:
        raise LifecycleError(
            f"{label} must be restriction-only; unsupported fields: {unsupported}"
        )
    schema = config.get("$schema")
    if schema is not None and (not isinstance(schema, str) or not schema):
        raise LifecycleError(f"{label} has an invalid restriction-only $schema")
    _validate_restriction_only_permission(
        config.get("permission"), label=f"{label}.permission"
    )
    _validate_restriction_only_tools(config.get("tools"), label=f"{label}.tools")
    agents = config.get("agent")
    if agents in (None, {}):
        return
    if not isinstance(agents, dict):
        raise LifecycleError(f"{label}.agent must be a restriction-only object")
    for agent_id, entry in agents.items():
        if (
            agent_id not in MANAGED_AGENT_IDS
            or not isinstance(entry, dict)
            or set(entry) - {"permission", "tools"}
        ):
            raise LifecycleError(f"{label}.agent must be restriction-only")
        _validate_restriction_only_permission(
            entry.get("permission"), label=f"{label}.agent.{agent_id}.permission"
        )
        _validate_restriction_only_tools(
            entry.get("tools"), label=f"{label}.agent.{agent_id}.tools"
        )


def _project_opencode_config_paths(project_root: Path) -> tuple[Path, ...]:
    return tuple(
        _resolved(path)
        for directory in _managed_project_directories(project_root)
        for path in (
            directory / "opencode.json",
            directory / "opencode.jsonc",
            directory / ".opencode/opencode.json",
            directory / ".opencode/opencode.jsonc",
        )
    )


def _validate_project_opencode_directories(project_root: Path) -> tuple[tuple[str, str], ...]:
    """Reject project V2 discovery entries outside reviewed restriction files."""

    fingerprint: list[tuple[str, str]] = []
    allowed = {"opencode.json", "opencode.jsonc"}
    for directory in _managed_project_directories(project_root):
        root = directory / ".opencode"
        if not root.exists() and not root.is_symlink():
            fingerprint.append((str(root), "absent"))
            continue
        try:
            observed = root.lstat()
            entries = tuple(sorted(root.iterdir(), key=lambda path: path.name))
        except OSError as exc:
            raise LifecycleError(f"could not inspect project OpenCode directory {root}: {exc}") from exc
        if stat.S_ISLNK(observed.st_mode) or not stat.S_ISDIR(observed.st_mode):
            raise LifecycleError(f"managed project OpenCode directory is unsafe: {root}")
        unexpected = [entry.name for entry in entries if entry.name not in allowed]
        if unexpected:
            raise LifecycleError(
                "managed sessions reject unmanaged project OpenCode entry: "
                f"{root / unexpected[0]}"
            )
        fingerprint.append((str(root), ",".join(entry.name for entry in entries)))
    return tuple(fingerprint)


def _load_project_permission_overlays(project_root: Path) -> tuple[dict[str, Any], ...]:
    """Read only deny/ask-bearing project config while native discovery is off."""

    files: list[Path] = []
    for directory in _managed_project_directories(project_root):
        files.extend(
            (
                directory / "opencode.json",
                directory / "opencode.jsonc",
                directory / ".opencode/opencode.json",
                directory / ".opencode/opencode.jsonc",
            )
        )
    overlays: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for path in files:
        resolved = _resolved(path)
        key = _portable_absolute_path_key(resolved)
        if key in seen:
            continue
        seen.add(key)
        if not resolved.exists() and not resolved.is_symlink():
            continue
        config, _content = _parse_opencode_jsonc(resolved)
        selected = {
            field: config[field]
            for field in ("permission", "tools", "agent")
            if field in config
        }
        if _contains_opencode_substitution(selected):
            raise LifecycleError(
                "managed project permission overlays forbid OpenCode {env:...} "
                "and {file:...} substitution tokens"
            )
        overlays.append(
            selected
        )
    return tuple(overlays)


def _contains_opencode_substitution(value: object) -> bool:
    if isinstance(value, str):
        lowered = value.lower()
        return "{env:" in lowered or "{file:" in lowered
    if isinstance(value, Mapping):
        return any(
            _contains_opencode_substitution(key)
            or _contains_opencode_substitution(child)
            for key, child in value.items()
        )
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return any(_contains_opencode_substitution(child) for child in value)
    return False


def _read_project_instruction_snapshot(
    project_root: Path,
) -> tuple[tuple[str, bytes], ...]:
    """Read the exact top-level AGENTS/CONTEXT chain in one bounded snapshot."""

    project_root = _resolved(project_root)
    directories = tuple(reversed(_managed_project_directories(project_root)))
    selected: list[tuple[str, bytes]] = []
    aggregate_size = 0
    for filename in ("AGENTS.md", "CONTEXT.md"):
        matches: list[tuple[str, bytes]] = []
        for directory in directories:
            candidate = directory / filename
            if not candidate.exists() and not candidate.is_symlink():
                continue
            content = _regular_file_bytes(
                candidate,
                label="project instruction",
                max_bytes=MAX_FILE_BYTES,
            )
            try:
                resolved = candidate.resolve(strict=True)
            except OSError as exc:
                raise LifecycleError(
                    f"could not resolve project instruction {candidate}: {exc}"
                ) from exc
            if not _is_within(resolved, project_root):
                raise LifecycleError(
                    f"project instruction resolves outside the project: {candidate}"
                )
            aggregate_size += len(content)
            if aggregate_size > MAX_DISTRIBUTION_BYTES:
                raise LifecycleError("project instruction chain exceeds safety limit")
            matches.append((str(resolved), content))
        if matches:
            selected = matches
            break
    return tuple(selected)


def _project_instruction_identity(
    snapshot: Sequence[tuple[str, bytes]],
) -> tuple[tuple[str, ...], str]:
    selected = [(path, _sha256(content)) for path, content in snapshot]
    canonical = json.dumps(selected, ensure_ascii=False, separators=(",", ":"))
    return tuple(path for path, _digest in selected), _sha256(
        canonical.encode("utf-8")
    )


def _project_instruction_snapshot(
    project_root: Path,
) -> tuple[tuple[str, ...], str]:
    """Mirror the pinned project AGENTS/CONTEXT system-instruction chain."""

    return _project_instruction_identity(_read_project_instruction_snapshot(project_root))


def _stage_project_instruction_snapshot(
    project_root: Path,
    config: Path,
    *,
    expected_paths: Sequence[str],
    expected_fingerprint: str,
) -> tuple[tuple[str, ...], dict[PurePosixPath, str]]:
    """Copy the verified instruction bytes into the soon-to-be-sealed config."""

    snapshot = _read_project_instruction_snapshot(project_root)
    if _project_instruction_identity(snapshot) != (
        tuple(expected_paths),
        expected_fingerprint,
    ):
        raise LifecycleError("project instruction chain changed before staging")
    relative_root = PurePosixPath("managed-project-instructions")
    destination_root = config.joinpath(*relative_root.parts)
    try:
        destination_root.mkdir(mode=0o700)
    except OSError as exc:
        raise LifecycleError("could not create staged project instructions") from exc
    staged_paths: list[str] = []
    staged_files: dict[PurePosixPath, str] = {}
    for index, (source_path, content) in enumerate(snapshot):
        relative = relative_root / f"{index:03d}-{Path(source_path).name}"
        destination = config.joinpath(*relative.parts)
        try:
            with destination.open("xb") as output:
                output.write(content)
            destination.chmod(0o444)
            resolved_destination = destination.resolve(strict=True)
        except OSError as exc:
            raise LifecycleError("could not stage project instruction") from exc
        digest = _sha256(content)
        staged_content = _regular_file_bytes(
            resolved_destination,
            label="staged project instruction",
            max_bytes=MAX_FILE_BYTES,
        )
        if _sha256(staged_content) != digest:
            raise LifecycleError("staged project instruction changed while copying")
        staged_paths.append(str(resolved_destination))
        staged_files[relative] = digest
    return tuple(staged_paths), staged_files


def _validate_staged_config_extras(
    config: Path, staged_files: Mapping[PurePosixPath, str]
) -> str:
    """Re-read sealed transient config files and return a stable content digest."""

    observed: list[tuple[str, str]] = []
    for relative, expected_digest in sorted(
        staged_files.items(), key=lambda item: item[0].as_posix()
    ):
        path = config.joinpath(*relative.parts)
        content, metadata = _regular_file(
            path,
            label="sealed config extra",
            max_bytes=MAX_FILE_BYTES,
        )
        if stat.S_IMODE(metadata.st_mode) != 0o444 or _sha256(content) != expected_digest:
            raise LifecycleError("sealed config extra changed")
        observed.append((relative.as_posix(), expected_digest))
    canonical = json.dumps(observed, separators=(",", ":"))
    return _sha256(canonical.encode("utf-8"))


def _validate_sealed_empty_directory(path: Path, *, label: str) -> tuple[int, int]:
    """Require one manager-owned discovery root to stay sealed and empty."""

    try:
        observed = path.lstat()
        entries = tuple(path.iterdir())
    except OSError as exc:
        raise LifecycleError(f"could not inspect {label}: {exc}") from exc
    if stat.S_ISLNK(observed.st_mode) or not stat.S_ISDIR(observed.st_mode):
        raise LifecycleError(f"{label} is not a real directory")
    if observed.st_mode & 0o222:
        raise LifecycleError(f"{label} must be read-only")
    if entries:
        raise LifecycleError(f"{label} must stay empty")
    return observed.st_dev, observed.st_ino


def _scan_managed_opencode_extensions(
    project_root: Path, environment: Mapping[str, str]
) -> str:
    """Reject executable extension surfaces and fingerprint config absence/bytes."""

    config_files, plugin_roots, tool_roots, skill_roots = _managed_opencode_search_roots(
        project_root, environment
    )
    project_config_keys = {
        _portable_absolute_path_key(path)
        for path in _project_opencode_config_paths(project_root)
    }
    fingerprint: list[tuple[str, str]] = list(
        _validate_project_opencode_directories(project_root)
    )
    global_config_root = _resolved(
        Path(environment.get("XDG_CONFIG_HOME", str(_account_home() / ".config")))
        / "opencode"
    )
    legacy = global_config_root / "config"
    if legacy.exists() or legacy.is_symlink():
        raise LifecycleError(
            "managed Grillmester sessions reject OpenCode's legacy executable "
            f"global config: {legacy}"
        )
    fingerprint.append((str(legacy), "absent"))

    # OpenCode loads its TUI config through a separate path from debug config.
    # It is therefore outside the resolved-config proof below and may trigger
    # dependency/package initialization before the permission policy applies.
    # Native unmanaged cplt remains the opt-in path for custom TUI settings.
    for tui_root in (global_config_root, _resolved(_account_home()) / ".opencode"):
        for tui_config in (tui_root / "tui.json", tui_root / "tui.jsonc"):
            if tui_config.exists() or tui_config.is_symlink():
                raise LifecycleError(
                    "managed Grillmester sessions reject ambient OpenCode TUI config "
                    f"outside the resolved-config proof: {tui_config}"
                )
            fingerprint.append((str(tui_config), "absent"))

    for path in config_files:
        if not path.exists() and not path.is_symlink():
            fingerprint.append((str(path), "absent"))
            continue
        config, content = _parse_opencode_jsonc(path)
        if _portable_absolute_path_key(_resolved(path)) in project_config_keys:
            _validate_restriction_only_project_config(config, label=str(path))
        _reject_declared_opencode_extensions(config, label=str(path))
        fingerprint.append((str(path), _sha256(content)))

    for root in plugin_roots:
        if not root.exists() and not root.is_symlink():
            fingerprint.append((str(root), "absent"))
            continue
        try:
            observed = root.lstat()
        except OSError as exc:
            raise LifecycleError(f"could not inspect OpenCode plugin path {root}: {exc}") from exc
        if stat.S_ISLNK(observed.st_mode) or not stat.S_ISDIR(observed.st_mode):
            raise LifecycleError(f"managed OpenCode plugin path is unsafe: {root}")
        try:
            entries = list(root.iterdir())
        except OSError as exc:
            raise LifecycleError(f"could not list OpenCode plugin path {root}: {exc}") from exc
        if entries:
            raise LifecycleError(
                "managed Grillmester sessions forbid auto-discovered OpenCode "
                f"plugins: {root}"
            )
        fingerprint.append((str(root), "empty"))

    # `debug agent` initializes ToolRegistry, which imports each discovered
    # JavaScript/TypeScript custom tool even under OPENCODE_PURE.  Skills are
    # also loaded from every config directory; rejecting external roots avoids
    # prompt injection and nondeterministic same-ID shadowing before the origin
    # probe can run.
    for kind, roots in (("tools", tool_roots), ("skills", skill_roots)):
        for root in roots:
            if not root.exists() and not root.is_symlink():
                fingerprint.append((str(root), "absent"))
                continue
            try:
                observed = root.lstat()
            except OSError as exc:
                raise LifecycleError(
                    f"could not inspect OpenCode {kind} path {root}: {exc}"
                ) from exc
            if stat.S_ISLNK(observed.st_mode) or not stat.S_ISDIR(observed.st_mode):
                raise LifecycleError(f"managed OpenCode {kind} path is unsafe: {root}")
            try:
                entries = list(root.iterdir())
            except OSError as exc:
                raise LifecycleError(
                    f"could not list OpenCode {kind} path {root}: {exc}"
                ) from exc
            if entries:
                raise LifecycleError(
                    f"managed Grillmester sessions forbid auto-discovered "
                    f"OpenCode {kind}: {root}"
                )
            fingerprint.append((str(root), "empty"))
    canonical = json.dumps(fingerprint, ensure_ascii=False, separators=(",", ":"))
    return _sha256(canonical.encode("utf-8"))


def _effective_repo_cplt_configuration(
    project_root: Path, environment: Mapping[str, str]
) -> Mapping[str, Any] | None:
    """Mirror pinned cplt's committed-config preference for security review."""

    git_environment = {
        name: environment[name]
        for name in ("LANG", "LC_ALL")
        if name in environment
    }
    git_environment.update(
        {
            "PATH": _trusted_system_path(),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    try:
        returncode, stdout, _stderr = _bounded_subprocess_output(
            ["git", "cat-file", "blob", "HEAD:.cplt.toml"],
            cwd=project_root,
            environment=git_environment,
            label="committed repository cplt config probe",
            max_bytes=MAX_JSON_BYTES,
        )
    except LifecycleError as exc:
        if "could not start" not in str(exc):
            raise
        returncode, stdout = 1, b""
    if returncode == 0:
        try:
            value = tomllib.loads(stdout.decode("utf-8"))
        except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
            raise LifecycleError(
                f"cannot validate committed repository .cplt.toml: {exc}"
            ) from exc
        return _validate_repo_cplt_configuration(value)

    # Pinned cplt ignores an uncommitted fallback on Linux because Landlock cannot
    # deny writes to one file inside the writable project directory.
    if sys.platform.startswith("linux"):
        return None
    value = _parse_cplt_toml(
        project_root / ".cplt.toml", label="repository cplt config"
    )
    return None if value is None else _validate_repo_cplt_configuration(value)


def _validate_repo_cplt_configuration(
    config: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Mirror pinned cplt's fail-closed repository deny schema.

    Pinned cplt drops the entire repository config on a serde or safety error.
    The manager must therefore reject the same malformed shapes instead of
    reasoning about a deny that cplt will silently omit.
    """

    unknown = sorted(set(config) - {"deny", "propose"})
    if unknown:
        raise LifecycleError(
            f"repository cplt config has unsupported top-level keys: {unknown}"
        )
    deny = config.get("deny", {})
    if not isinstance(deny, dict):
        raise LifecycleError("repository cplt config [deny] must be a table")
    unknown_deny = sorted(set(deny) - {"env", "paths"})
    if unknown_deny:
        raise LifecycleError(
            f"repository cplt config [deny] has unsupported keys: {unknown_deny}"
        )
    denied_environment = deny.get("env", [])
    if not isinstance(denied_environment, list) or any(
        not isinstance(name, str)
        or not name
        or any(not (character.isascii() and (character.isalnum() or character == "_")) for character in name)
        for name in denied_environment
    ):
        raise LifecycleError(
            "repository cplt config deny.env must contain [A-Za-z0-9_] identifiers"
        )
    denied_paths = deny.get("paths", [])
    unsafe = {'"', ")", "(", ";", "\\", "\n", "\r", "\0"}
    if not isinstance(denied_paths, list) or any(
        not isinstance(value, str)
        or ".." in Path(value).parts
        or any(character in value for character in unsafe)
        for value in denied_paths
    ):
        raise LifecycleError(
            "repository cplt config deny.paths contains traversal or unsafe characters"
        )
    propose = config.get("propose", {})
    if not isinstance(propose, dict):
        raise LifecycleError("repository cplt config [propose] must be a table")
    return config


def _check_local_only_cplt_configuration(
    project_root: Path,
    environment: Mapping[str, str],
    *,
    protected_environment: Iterable[str] = (),
    instruction_paths: Sequence[str] = (),
) -> None:
    """Reject every repo proposal; the isolated global config has no trust store."""

    repo_config = _effective_repo_cplt_configuration(project_root, environment)
    if repo_config is None:
        return
    _validate_cplt_deny_environment(
        repo_config,
        label="repository cplt config",
        protected=protected_environment,
    )
    _validate_cplt_instruction_visibility(
        repo_config,
        base=project_root,
        label="repository cplt config",
        instruction_paths=instruction_paths,
    )
    if set(repo_config) - {"deny", "propose"}:
        raise LifecycleError("local-only rejects unknown repository cplt sections")
    proposed = repo_config.get("propose")
    if proposed not in (None, {}):
        raise LifecycleError(
            "local-only rejects every repository .cplt.toml [propose] relaxation"
        )


def _policy_path(value: str, *, base: Path) -> Path:
    if value == "~":
        candidate = _account_home()
    elif value.startswith("~/"):
        candidate = _account_home() / value[2:]
    else:
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = base / candidate
    return _resolved(candidate)


def _write_paths_from_cplt_config(
    config: Mapping[str, Any] | None, *, base: Path, label: str
) -> tuple[Path, ...]:
    if config is None:
        return ()
    allow = config.get("allow")
    if allow is None:
        return ()
    if not isinstance(allow, dict):
        raise LifecycleError(f"{label} [allow] must be a table")
    values = allow.get("write", [])
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        raise LifecycleError(f"{label} allow.write must be a string array")
    return tuple(_policy_path(value, base=base) for value in values)


def _deny_paths_from_cplt_config(
    config: Mapping[str, Any] | None, *, base: Path, label: str
) -> tuple[Path, ...]:
    """Resolve cplt deny paths using the exact source-specific base directory."""

    if config is None:
        return ()
    deny = _require_table(config, "deny", label=label)
    values = deny.get("paths", [])
    if not isinstance(values, list) or any(
        not isinstance(value, str) or not value for value in values
    ):
        raise LifecycleError(f"{label} deny.paths must be a non-empty string array")
    return tuple(_policy_path(value, base=base) for value in values)


def _validate_cplt_instruction_visibility(
    config: Mapping[str, Any] | None,
    *,
    base: Path,
    label: str,
    instruction_paths: Sequence[str],
) -> None:
    """Reject cplt denies that can silently hide reviewed project instructions."""

    instructions = tuple(_resolved(Path(value)) for value in instruction_paths)
    for denied in _deny_paths_from_cplt_config(config, base=base, label=label):
        for instruction in instructions:
            if _paths_overlap(denied, instruction):
                raise LifecycleError(
                    f"{label} deny.paths hides a managed project instruction"
                )


def _check_effective_cplt_instruction_visibility(
    project_root: Path,
    environment: Mapping[str, str],
    instruction_paths: Sequence[str],
) -> None:
    """Check both effective cplt config layers against staged instruction copies."""

    global_config, global_base = _global_cplt_configuration(environment)
    _validate_cplt_instruction_visibility(
        global_config,
        base=global_base,
        label="global cplt config",
        instruction_paths=instruction_paths,
    )
    repo_config = _effective_repo_cplt_configuration(project_root, environment)
    _validate_cplt_instruction_visibility(
        repo_config,
        base=project_root,
        label="repository cplt config",
        instruction_paths=instruction_paths,
    )


def _require_table(
    config: Mapping[str, Any], name: str, *, label: str
) -> Mapping[str, Any]:
    value = config.get(name, {})
    if not isinstance(value, dict):
        raise LifecycleError(f"{label} [{name}] must be a table")
    return value


def _validate_cplt_deny_environment(
    config: Mapping[str, Any] | None,
    *,
    label: str,
    protected: Iterable[str] = (),
) -> None:
    if config is None:
        return
    deny = _require_table(config, "deny", label=label)
    denied = deny.get("env", [])
    if not isinstance(denied, list) or any(not isinstance(name, str) for name in denied):
        raise LifecycleError(f"{label} deny.env must be a string array")
    protected_names = {
        "PWD",
        "CPLT_CONFIG",
        "OPENCODE_CONFIG_DIR",
        "OPENCODE_MODELS_PATH",
        *BASE_PROFILE_ENVIRONMENT,
        *LOCAL_ONLY_ENVIRONMENT,
        *MANAGER_DYNAMIC_ENVIRONMENT,
        *protected,
    }
    conflicts = sorted(set(denied) & protected_names)
    if conflicts:
        raise LifecycleError(
            f"{label} deny.env strips manager-controlled runtime variables: "
            + ", ".join(conflicts)
        )


def _validate_normal_cplt_configuration(
    config: Mapping[str, Any] | None, *, label: str
) -> None:
    """Allow machine compatibility settings, but reject hidden relaxations."""

    if config is None:
        return
    known_sections = {
        "config_version",
        "proxy",
        "allow",
        "deny",
        "sandbox",
        "gh_guard",
        "git_guard",
        "audit",
    }
    unknown = sorted(set(config) - known_sections)
    if unknown:
        raise LifecycleError(f"{label} has unsupported top-level keys: {unknown}")
    _validate_cplt_deny_environment(config, label=label)

    allow = _require_table(config, "allow", label=label)
    for key in ("read", "write", "socket", "ports", "localhost"):
        if allow.get(key):
            raise LifecycleError(
                f"{label} allow.{key} is a hidden relaxation; pass access through "
                "the Grillmester launcher instead"
            )

    sandbox = _require_table(config, "sandbox", label=label)
    if sandbox.get("pass_env"):
        raise LifecycleError(
            f"{label} sandbox.pass_env is forbidden; use explicit --pass-env"
        )
    if sandbox.get("inherit_env") is True:
        raise LifecycleError(f"{label} sandbox.inherit_env=true is forbidden")
    dangerous_true = {
        "allow_env_files",
        "allow_localhost_any",
        "allow_lifecycle_scripts",
        "allow_gpg_signing",
        "allow_jvm_attach",
        "gradle_init",
        "allow_docker",
        "allow_tmp_exec",
        "allow_cache_exec_any",
        "allow_browser",
    }
    enabled = sorted(key for key in dangerous_true if sandbox.get(key) is True)
    if enabled or sandbox.get("allow_cache_exec"):
        raise LifecycleError(
            f"{label} enables hidden sandbox relaxations: "
            + ", ".join(enabled or ["allow_cache_exec"])
        )
    if sandbox.get("validate") is False:
        raise LifecycleError(f"{label} cannot disable sandbox validation")
    if sandbox.get("scratch_dir") is False:
        raise LifecycleError(
            f"{label} cannot disable cplt scratch; strict gh/git guards require it"
        )

    proxy = _require_table(config, "proxy", label=label)
    disabled_guards = sorted(
        key
        for key in ("default_allowlist", "enabled", "forced")
        if proxy.get(key) is False
    )
    if disabled_guards:
        raise LifecycleError(
            f"{label} disables required proxy guards: "
            + ", ".join(f"proxy.{key}=false" for key in disabled_guards)
        )
    for key in ("allowed_domains", "allow_private_domains"):
        if proxy.get(key):
            raise LifecycleError(
                f"{label} proxy.{key} is a hidden network relaxation"
            )
    for section in ("gh_guard", "git_guard"):
        if _require_table(config, section, label=label):
            raise LifecycleError(
                f"{label} [{section}] must be empty when Grillmester pins strict guards"
            )


def _global_cplt_configuration(
    environment: Mapping[str, str]
) -> tuple[Mapping[str, Any] | None, Path]:
    configured = environment.get("CPLT_CONFIG")
    if configured:
        path = _policy_path(configured, base=_resolved(Path.cwd()))
    else:
        path = _resolved(_account_home()) / ".config/cplt/config.toml"
    if path == Path("/dev/null"):
        return None, path.parent
    return _parse_cplt_toml(path, label="global cplt config"), path.parent


def _cplt_configuration_snapshot(
    project_root: Path,
    environment: Mapping[str, str],
    *,
    include_global: bool = True,
) -> tuple[Mapping[str, Any] | None, str | None, Mapping[str, Any] | None]:
    """Capture parsed cplt inputs for same-process drift detection.

    This narrows accidental and ordinary concurrent-change windows. It is not a
    sealed input to cplt: the pinned client still rereads repository configuration
    immediately after this manager starts it.
    """

    if include_global:
        global_config, global_base = _global_cplt_configuration(environment)
        base: str | None = str(global_base)
    else:
        global_config, base = None, None
    repo_config = _effective_repo_cplt_configuration(project_root, environment)
    return copy.deepcopy(global_config), base, copy.deepcopy(repo_config)


def _require_cplt_configuration_unchanged(
    project_root: Path,
    environment: Mapping[str, str],
    expected: tuple[Mapping[str, Any] | None, str | None, Mapping[str, Any] | None],
    *,
    include_global: bool = True,
) -> None:
    """Fail when a validated cplt input changes before the next launch step."""

    if _cplt_configuration_snapshot(
        project_root, environment, include_global=include_global
    ) != expected:
        raise LifecycleError("cplt configuration changed during managed preflight")


def _check_cplt_stage_write_overlap(
    home: Path,
    project_root: Path,
    environment: Mapping[str, str],
    *,
    protected_environment: Iterable[str] = (),
    instruction_paths: Sequence[str] = (),
) -> None:
    """Reject user-configured write grants that cover immutable runtime policy."""

    global_config, global_base = _global_cplt_configuration(environment)
    _validate_cplt_deny_environment(
        global_config,
        label="global cplt config",
        protected=protected_environment,
    )
    _validate_cplt_instruction_visibility(
        global_config,
        base=global_base,
        label="global cplt config",
        instruction_paths=instruction_paths,
    )
    roots = list(
        _write_paths_from_cplt_config(
            global_config, base=global_base, label="global cplt config"
        )
    )
    repo_config = _effective_repo_cplt_configuration(project_root, environment)
    if repo_config is not None:
        _validate_cplt_deny_environment(
            repo_config,
            label="repository cplt config",
            protected=protected_environment,
        )
        _validate_cplt_instruction_visibility(
            repo_config,
            base=project_root,
            label="repository cplt config",
            instruction_paths=instruction_paths,
        )
        propose = repo_config.get("propose")
        if propose is not None and not isinstance(propose, dict):
            raise LifecycleError("repository cplt [propose] must be a table")
        if propose not in (None, {}):
            raise LifecycleError(
                "Grillmester profiles reject every repository .cplt.toml "
                "[propose] relaxation"
            )
        roots.extend(
            _write_paths_from_cplt_config(
                propose if isinstance(propose, dict) else None,
                base=project_root,
                label="repository cplt proposal",
            )
        )
    for name in CPLT_WRITABLE_TOOL_ENVIRONMENT:
        raw = environment.get(name)
        if not raw:
            continue
        values = raw.split(os.pathsep) if name == "GOPATH" else [raw]
        roots.extend(_policy_path(value, base=_account_home()) for value in values if value)
    for root in roots:
        if _paths_overlap(home, root):
            raise LifecycleError(
                "cplt write policy overlaps Grillmester's immutable lifecycle home: "
                f"{root}"
            )
    _validate_normal_cplt_configuration(global_config, label="global cplt config")
    if global_config is not None:
        proxy = _require_table(global_config, "proxy", label="global cplt config")
        audit = _require_table(global_config, "audit", label="global cplt config")
        output_paths: list[Path] = []
        log_file = proxy.get("log_file")
        if isinstance(log_file, str) and log_file:
            output_paths.append(_policy_path(log_file, base=global_base))
        destination = audit.get("destination")
        if isinstance(destination, str) and destination and destination != "stderr":
            output_paths.append(_policy_path(destination, base=global_base))
        for output_path in output_paths:
            if _paths_overlap(home, output_path):
                raise LifecycleError(
                    "cplt host output path overlaps Grillmester's immutable lifecycle "
                    f"home: {output_path}"
                )


def _check_local_only_platform() -> None:
    if sys.platform == "darwin":
        return
    if sys.platform.startswith("linux"):
        raise LifecycleError(
            "local-only requires macOS Seatbelt with pinned cplt; cplt's Linux "
            "network policy cannot pin the forced-proxy port to localhost"
        )
    raise LifecycleError(
        f"local-only is unsupported on platform {platform.system() or sys.platform!r}"
    )


def _trusted_system_path() -> str:
    """Return only root-owned, non-writable system executable directories."""

    trusted: list[Path] = []
    for configured in ("/usr/bin", "/bin", "/usr/sbin", "/sbin"):
        try:
            resolved = Path(configured).resolve(strict=True)
            observed = resolved.stat()
        except OSError:
            continue
        if not stat.S_ISDIR(observed.st_mode):
            continue
        if observed.st_mode & 0o022:
            continue
        if hasattr(os, "geteuid") and observed.st_uid != 0:
            continue
        if not any(_same_path(resolved, present) for present in trusted):
            trusted.append(resolved)
    if not trusted:
        raise LifecycleError("no root-owned system executable directory is available")
    return os.pathsep.join(str(path) for path in trusted)


def _temporary_write_roots() -> tuple[Path, ...]:
    roots: list[Path] = []
    for raw in ("/tmp", "/private/tmp", "/var/tmp", tempfile.gettempdir()):
        candidate = _resolved(Path(raw))
        if not any(_same_path(candidate, existing) for existing in roots):
            roots.append(candidate)
    return tuple(roots)


def _managed_untrusted_path_roots(
    *,
    environment: Mapping[str, str],
    project_root: Path,
    home: Path,
    runtime_root: Path,
) -> tuple[Path, ...]:
    account_home = _resolved(_account_home())
    roots = [
        _resolved(project_root),
        _resolved(home),
        _resolved(runtime_root),
        *_temporary_write_roots(),
        *_ambient_opencode_write_roots(environment),
        account_home / ".bun",
        account_home / ".deno",
        account_home / ".asdf/shims",
        account_home / ".cache/cplt/tmp",
        account_home / ".local/share/mise",
        account_home / ".local/share/pnpm",
        account_home / ".local/share/uv",
        account_home / "Library/Caches",
        account_home / "Library/pnpm",
    ]
    for name, suffixes in (
        ("XDG_CACHE_HOME", (PurePosixPath("."),)),
        ("XDG_RUNTIME_DIR", (PurePosixPath("."),)),
        (
            "XDG_DATA_HOME",
            tuple(PurePosixPath(value) for value in ("mise", "pnpm", "uv", "opencode")),
        ),
    ):
        raw = environment.get(name)
        if not raw:
            continue
        base = Path(raw)
        if not base.is_absolute():
            raise LifecycleError(f"{name} must be absolute when explicitly set")
        roots.extend(base.joinpath(*suffix.parts) for suffix in suffixes)
    return tuple(_resolved(path) for path in roots)


def _validated_tool_environment(
    environment: Mapping[str, str],
    *,
    project_root: Path,
    home: Path,
    runtime_root: Path,
) -> dict[str, str]:
    forbidden = _managed_untrusted_path_roots(
        environment=environment,
        project_root=project_root,
        home=home,
        runtime_root=runtime_root,
    )
    result: dict[str, str] = {}
    account_home = _resolved(_account_home())
    for name, default_subpath in DEFAULT_ONLY_CPLT_TOOL_ENVIRONMENT.items():
        raw = environment.get(name)
        if not raw:
            continue
        candidate = Path(raw)
        if not candidate.is_absolute():
            raise LifecycleError(f"{name} tool path must be absolute: {raw!r}")
        resolved = _resolved(candidate)
        default = (
            None
            if default_subpath is None
            else _resolved(account_home / default_subpath)
        )
        if not _is_within(resolved, project_root) and (
            default is None or not _same_path(resolved, default)
        ):
            raise LifecycleError(
                f"{name} custom root is not sandbox-granted by pinned cplt: {resolved}"
            )
        result[name] = raw
    for name in SAFE_CPLT_TOOL_ENVIRONMENT:
        raw = environment.get(name)
        if not raw:
            continue
        values = raw.split(os.pathsep) if name in LIST_TOOL_ENVIRONMENT else [raw]
        if not values or any(not value for value in values):
            raise LifecycleError(f"{name} contains an empty tool path")
        overlaps_forbidden_root = False
        for value in values:
            candidate = Path(value)
            if not candidate.is_absolute():
                raise LifecycleError(f"{name} tool path must be absolute: {value!r}")
            resolved = _resolved(candidate)
            if any(_paths_overlap(resolved, root) for root in forbidden):
                overlaps_forbidden_root = True
        if overlaps_forbidden_root:
            # cplt already grants some platform-default tool roots (notably
            # ~/Library/pnpm on macOS) independently of these variables.
            # Omitting the complete variable avoids advertising an unsafe root
            # without turning a normal shell setup into a launch failure.
            continue
        result[name] = raw
    return result


def _managed_subprocess_path(
    trusted_directory: Path | None = None,
    *,
    environment: Mapping[str, str] | None = None,
    project_root: Path | None = None,
    home: Path | None = None,
    runtime_root: Path | None = None,
) -> str:
    entries = [] if trusted_directory is None else [str(_resolved(trusted_directory))]
    entries.extend(_trusted_system_path().split(os.pathsep))
    if environment is None:
        return os.pathsep.join(entries)
    if project_root is None or home is None or runtime_root is None:
        raise LifecycleError("managed PATH filtering requires lifecycle boundaries")
    forbidden = _managed_untrusted_path_roots(
        environment=environment,
        project_root=project_root,
        home=home,
        runtime_root=runtime_root,
    )
    for raw in environment.get("PATH", os.defpath).split(os.pathsep):
        candidate = Path(raw)
        if not raw or not candidate.is_absolute():
            continue
        try:
            resolved = candidate.resolve(strict=True)
            observed = resolved.stat()
        except OSError:
            continue
        if not stat.S_ISDIR(observed.st_mode):
            continue
        if any(_paths_overlap(resolved, root) for root in forbidden):
            continue
        if sys.platform.startswith("linux"):
            bwrap = resolved / "bwrap"
            try:
                if bwrap.is_file() and os.access(bwrap, os.X_OK):
                    # Pinned cplt executes PATH bwrap before Landlock/seccomp.
                    continue
            except OSError:
                continue
        if any(_same_path(resolved, Path(existing)) for existing in entries):
            continue
        entries.append(str(resolved))
    return os.pathsep.join(entries)


def _runtime_environment(
    environment: Mapping[str, str],
    inputs: RuntimeInputs,
    *,
    direct: bool,
    project_root: Path | None = None,
    home: Path | None = None,
    runtime_root: Path | None = None,
) -> dict[str, str]:
    """Keep direct/local-only hermetic and let normal cplt own its environment."""

    result = {
        name: environment[name]
        for name in SAFE_CPLT_HOST_ENVIRONMENT
        if name in environment
    }
    result["HOME"] = str(_resolved(_account_home()))
    result["PWD"] = str(_resolved(Path.cwd()))
    if direct:
        result["PATH"] = environment.get("PATH", os.defpath)
    else:
        if project_root is None or home is None or runtime_root is None:
            raise LifecycleError("managed environment requires lifecycle boundaries")
        result.update(
            _validated_tool_environment(
                environment,
                project_root=project_root,
                home=home,
                runtime_root=runtime_root,
            )
        )
        result["PATH"] = _managed_subprocess_path(
            environment=environment,
            project_root=project_root,
            home=home,
            runtime_root=runtime_root,
        )
    for name in inputs.pass_environment:
        result[name] = environment[name]
    result.update(inputs.profile.environment)
    return result


def _validate_managed_environment_roots(
    project_root: Path,
    home: Path,
    runtime_root: Path,
    environment: Mapping[str, str],
) -> None:
    for name in (
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_RUNTIME_DIR",
        "XDG_STATE_HOME",
    ):
        raw = environment.get(name)
        if not raw:
            continue
        candidate = Path(raw)
        if not candidate.is_absolute():
            raise LifecycleError(f"{name} must be absolute when explicitly set")
        root = _resolved(candidate)
        if _paths_overlap(root, project_root):
            raise LifecycleError(
                f"{name} must not overlap the writable OpenCode project"
            )
        if _is_within(root, home) or _is_within(root, runtime_root):
            raise LifecycleError(
                f"{name} must not be inside Grillmester lifecycle data"
            )


def _active_distribution(home: Path) -> tuple[str, VerifiedDistribution]:
    with _lifecycle_lock(home):
        state = _load_state(home, required=True)
        assert state is not None
        release_id = _validate_release_id(state.get("active"), field="active")
        return release_id, _release_distribution(home, release_id)


def _load_verified_permission_composer(
    distribution: VerifiedDistribution,
) -> types.ModuleType:
    """Load the exact composer pinned by this manager from verified active bytes."""

    entry = next(
        (
            item
            for item in distribution.entries
            if item.relative == PERMISSION_COMPOSER_RELATIVE
        ),
        None,
    )
    if entry is None:  # pragma: no cover - current distribution verifier requires it
        raise LifecycleError("active distribution has no permission composer")
    if entry.sha256 != PERMISSION_COMPOSER_SHA256:
        raise LifecycleError("active permission composer does not match manager pin")
    path = distribution.root.joinpath(*PERMISSION_COMPOSER_RELATIVE.parts)
    content = _regular_file_bytes(path, label="active permission composer")
    if _sha256(content) != entry.sha256:
        raise LifecycleError("active permission composer changed after verification")
    try:
        source = content.decode("utf-8")
        code = compile(source, str(path), "exec")
    except (UnicodeDecodeError, SyntaxError) as exc:
        raise LifecycleError(f"active permission composer is invalid Python: {exc}") from exc
    name = f"grillmester_permission_composer_{entry.sha256}"
    module = types.ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    try:
        exec(code, module.__dict__)
    except Exception as exc:
        sys.modules.pop(name, None)
        raise LifecycleError(f"could not load active permission composer: {exc}") from exc
    required = (
        "build_bounded_config_probe_content",
        "compose_policy",
        "parse_resolved_config",
        "require_no_external_extensions",
        "rewrite_staged_agents",
        "validate_effective_agent",
        "validate_hidden_native_agent",
        "validate_provider_contract",
        "validate_target_agent_ids",
        "validate_target_commands",
        "validate_skill_origins",
    )
    if getattr(module, "SCHEMA_VERSION", None) != 1 or any(
        not callable(getattr(module, name, None)) for name in required
    ):
        sys.modules.pop(name, None)
        raise LifecycleError("active permission composer has an invalid runtime contract")
    return module


def _composer_call(composer: types.ModuleType, operation: str, *args: Any) -> Any:
    function = getattr(composer, operation)
    error_type = getattr(composer, "PermissionCompositionError", Exception)
    try:
        return function(*args)
    except error_type:
        # Resolved config is untrusted and may contain values expanded from
        # {env:...}/{file:...}. Never echo a composer exception that might
        # interpolate those values into manager diagnostics.
        raise LifecycleError(
            f"OpenCode permission composition failed during {operation}"
        ) from None


def _normalize_resolved_provider_credentials(
    resolved_config: Mapping[str, Any],
    expected_providers: Mapping[str, Any],
    environment: Mapping[str, str],
) -> dict[str, Any]:
    """Normalize exact expanded API keys without exposing credential material."""

    normalized = copy.deepcopy(dict(resolved_config))
    actual_providers = normalized.get("provider")
    if actual_providers is None:
        actual_providers = {}
        normalized["provider"] = actual_providers
    if not isinstance(actual_providers, dict):
        raise LifecycleError("final resolved provider contract is invalid")
    for provider_id, expected_provider in expected_providers.items():
        if not isinstance(expected_provider, Mapping):
            raise LifecycleError("expected provider contract is invalid")
        expected_options = expected_provider.get("options")
        if not isinstance(expected_options, Mapping):
            continue
        expected_key = expected_options.get("apiKey")
        if expected_key is None:
            continue
        if not isinstance(expected_key, str):
            raise LifecycleError("expected provider credential contract is invalid")
        match = re.fullmatch(r"\{env:([A-Za-z_][A-Za-z0-9_]*)\}", expected_key)
        if match is None:
            raise LifecycleError("expected provider credential contract is invalid")
        actual_provider = actual_providers.get(provider_id)
        actual_options = (
            actual_provider.get("options")
            if isinstance(actual_provider, dict)
            else None
        )
        actual_key = (
            actual_options.get("apiKey")
            if isinstance(actual_options, dict)
            else None
        )
        expected_value = environment.get(match.group(1))
        if (
            not isinstance(actual_key, str)
            or expected_value is None
            or actual_key != expected_value
        ):
            raise LifecycleError("final resolved provider credential does not match")
        actual_options["apiKey"] = expected_key
    return normalized


def _parse_bounded_json_value(content: bytes, *, label: str) -> Any:
    try:
        return json.loads(
            content.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_nonstandard_json_constant,
        )
    except UnicodeDecodeError as exc:
        raise LifecycleError(f"{label} output is not UTF-8") from exc
    except (json.JSONDecodeError, RecursionError) as exc:
        raise LifecycleError(f"{label} did not return bounded valid JSON") from exc


def _validate_composed_opencode_session(
    composer: types.ModuleType,
    composed: Any,
    launch_command: Sequence[str],
    *,
    config: Path,
    config_probe: Path,
    preflight_project: Path,
    config_probe_content: str,
    environment: Mapping[str, str],
) -> dict[str, str]:
    """Validate actual ordered permissions and skill origins through pinned cplt."""

    raw_data_home = environment.get("XDG_DATA_HOME")
    if not isinstance(raw_data_home, str) or not Path(raw_data_home).is_absolute():
        raise LifecycleError("managed OpenCode XDG data home is not absolute")
    expected_tool_output_pattern = str(
        _resolved(Path(raw_data_home)) / "opencode" / "tool-output" / "*"
    )
    digests: dict[str, str] = {}
    final_config = _run_cplt_json_probe(
        launch_command,
        config=config_probe,
        preflight_project=preflight_project,
        client_arguments=("debug", "config"),
        environment=environment,
        label="sandboxed final OpenCode config probe",
        additional_read=config,
        config_content_override=config_probe_content,
    )
    resolved_config = _composer_call(
        composer, "parse_resolved_config", final_config
    )
    _composer_call(
        composer,
        "require_no_external_extensions",
        resolved_config,
        composed.instruction_paths,
    )
    digests["config"] = _sha256(final_config)
    normalized_provider_config = _normalize_resolved_provider_credentials(
        resolved_config,
        composed.provider_contract,
        environment,
    )
    digests["providers"] = _composer_call(
        composer,
        "validate_provider_contract",
        normalized_provider_config,
        composed.provider_contract,
    )
    digests["agents"] = _composer_call(
        composer,
        "validate_target_agent_ids",
        resolved_config,
        composed.agents,
        composed.agent_contracts,
        composed.runtime_agent,
    )
    digests["commands"] = _composer_call(
        composer,
        "validate_target_commands",
        resolved_config,
        composed.command_contracts,
    )

    for agent_id in composed.disabled_agent_ids:
        digests[f"disabled-agent:{agent_id}"] = _run_cplt_missing_agent_probe(
            launch_command,
            config=config,
            preflight_project=preflight_project,
            agent_id=agent_id,
            environment=environment,
        )

    for agent_id in composed.hidden_native_agent_ids:
        output = _run_cplt_json_probe(
            launch_command,
            config=config,
            preflight_project=preflight_project,
            client_arguments=("debug", "agent", agent_id),
            environment=environment,
            label=f"sandboxed hidden native agent probe for {agent_id}",
        )
        resolved_agent = _composer_call(
            composer, "parse_resolved_config", output
        )
        digests[f"hidden-agent:{agent_id}"] = _composer_call(
            composer,
            "validate_hidden_native_agent",
            agent_id,
            resolved_agent,
            expected_tool_output_pattern,
        )

    for agent_id in composed.enabled_agent_ids:
        intended = composed.agents[agent_id]
        output = _run_cplt_json_probe(
            launch_command,
            config=config,
            preflight_project=preflight_project,
            client_arguments=("debug", "agent", agent_id),
            environment=environment,
            label=f"sandboxed OpenCode agent probe for {agent_id}",
        )
        resolved_agent = _composer_call(
            composer, "parse_resolved_config", output
        )
        digests[f"agent:{agent_id}"] = _composer_call(
            composer,
            "validate_effective_agent",
            agent_id,
            resolved_agent,
            intended,
            composed.agent_contracts[agent_id],
            expected_tool_output_pattern,
        )

    skill_output = _run_cplt_json_probe(
        launch_command,
        config=config_probe,
        preflight_project=preflight_project,
        client_arguments=("debug", "skill"),
        environment=environment,
        label="sandboxed OpenCode skill-origin probe",
        additional_read=config,
        config_content_override=config_probe_content,
    )
    skills = _parse_bounded_json_value(
        skill_output, label="sandboxed OpenCode skill-origin probe"
    )
    digests["skills"] = _composer_call(
        composer, "validate_skill_origins", skills, config_probe
    )
    return digests


def _delegate_to_active_manager_if_needed(
    home: Path, arguments: Sequence[str]
) -> None:
    """Execute the manager bound to an older active runtime contract after rollback."""

    home = _resolved(home)
    with _lifecycle_lock(home):
        state = _load_state(home, required=True)
        assert state is not None
        release_id = _validate_release_id(state.get("active"), field="active")
        distribution = _release_distribution(
            home, release_id, require_current_contract=False
        )
        manager_entry = next(
            (
                entry
                for entry in distribution.entries
                if entry.relative == MANAGER_RELATIVE
            ),
            None,
        )
        if manager_entry is None:  # pragma: no cover - required by verifier
            raise LifecycleError("active distribution has no lifecycle manager")
        current_manager = Path(__file__).resolve(strict=True)
        if _sha256(
            _regular_file_bytes(current_manager, label="current lifecycle manager")
        ) == manager_entry.sha256:
            return
        active_manager = distribution.root.joinpath(*MANAGER_RELATIVE.parts)
    try:
        os.execv(
            sys.executable,
            [sys.executable, "-I", "-S", str(active_manager), *arguments],
        )
    except OSError as exc:  # pragma: no cover - process is replaced on success
        raise LifecycleError(
            f"could not delegate to active lifecycle manager {active_manager}: {exc}"
        ) from exc


def _build_cplt_command(
    executable: str,
    config: Path,
    models_catalog: Path,
    test_home: Path,
    policy: Path,
    project_root: Path,
    inputs: RuntimeInputs,
    client_arguments: Sequence[str],
) -> list[str]:
    profile = inputs.profile
    command = [
        executable,
        "--yes",
        "--scratch-dir",
        "--deny-clipboard",
        "--no-audit",
        "--no-quiet",
        "--agent",
        "opencode",
        "--project-dir",
        str(project_root),
        "--preset",
        "strict",
        "--with-proxy",
        "--proxy-forced",
        "--default-allowlist",
        "--gh-guard",
        "--git-guard",
        "--no-allow-localhost-any",
        "--no-allow-env-files",
        "--no-allow-tmp-exec",
        "--no-allow-docker",
        "--no-allow-lifecycle-scripts",
    ]
    command.extend(
        [
            "--allow-read",
            str(config),
            "--allow-read",
            str(models_catalog),
            "--allow-read",
            str(test_home),
            "--pass-env",
            "OPENCODE_CONFIG_DIR",
            "--pass-env",
            "OPENCODE_MODELS_PATH",
            "--pass-env",
            "OPENCODE_TEST_HOME",
            "--pass-env",
            "PWD",
            "--pass-env",
            "OPENCODE_AUTH_CONTENT",
            "--pass-env",
            "XDG_CACHE_HOME",
            "--pass-env",
            "XDG_CONFIG_HOME",
            "--pass-env",
            "XDG_DATA_HOME",
            "--pass-env",
            "XDG_STATE_HOME",
        ]
    )
    for name in sorted(profile.environment):
        command.extend(["--pass-env", name])
    for name in inputs.pass_environment:
        command.extend(["--pass-env", name])
    for port in inputs.local_ports:
        command.extend(["--allow-localhost", str(port)])
    for port in inputs.provider_ports:
        command.extend(["--allow-port", str(port)])
    for domain in inputs.private_provider_domains:
        command.extend(["--allow-private-domain", domain])

    if inputs.provider_domains:
        allowed = policy / "allowed-domains.txt"
        _write_policy_file(allowed, inputs.provider_domains)
        command.extend(["--allowed-domains", str(allowed)])
    elif profile.cplt_policy == "local-only":
        assert profile.allowed_domain is not None
        allowed = policy / "allowed-domains.txt"
        blocked = policy / "blocked-domains.txt"
        _write_policy_file(allowed, [profile.allowed_domain])
        _write_policy_file(
            blocked, [*profile.blocked_domains, LOCAL_ONLY_ALLOWED_DOMAIN]
        )
        command.extend(
            ["--allowed-domains", str(allowed), "--blocked-domains", str(blocked)]
        )

    command.append("--")
    command.extend(client_arguments)
    return command


def _check_opencode_version_inside_cplt(
    launch_command: Sequence[str],
    *,
    preflight_project: Path,
    environment: Mapping[str, str],
) -> None:
    """Execute untrusted OpenCode version code only inside pinned cplt."""

    command = list(launch_command)
    try:
        project_index = command.index("--project-dir") + 1
        delimiter = command.index("--")
    except ValueError as exc:  # pragma: no cover - internal command invariant
        raise LifecycleError("internal cplt command is missing required boundaries") from exc
    command[project_index] = str(preflight_project)
    prefix = [
        argument
        for argument in command[:delimiter]
        if argument not in {"--no-quiet", "--no-audit"}
    ]
    command = [*prefix, "--quiet", "--no-audit", "--", "--version"]
    _recheck_managed_command_executables(command, environment)
    returncode, stdout, stderr = _bounded_subprocess_output(
        command,
        environment=environment,
        label="sandboxed OpenCode version check",
    )
    try:
        observed_stdout = stdout.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise LifecycleError(
            "sandboxed OpenCode version output is not UTF-8; captured output is "
            "suppressed"
        ) from exc
    if (
        returncode != 0
        or observed_stdout != SUPPORTED_OPENCODE_VERSION
    ):
        raise LifecycleError(
            f"OpenCode must be exactly {SUPPORTED_OPENCODE_VERSION!r} inside cplt; "
            "captured output is suppressed because cplt startup diagnostics may "
            f"contain configured URLs or credentials (exit={returncode})"
        )


def _bounded_subprocess_output(
    command: Sequence[str],
    *,
    environment: Mapping[str, str],
    label: str,
    max_bytes: int | None = None,
    timeout_seconds: float | None = None,
    cwd: Path | None = None,
) -> tuple[int, bytes, bytes]:
    """Capture a subprocess without allowing unbounded stdout/stderr growth."""

    if max_bytes is None:
        max_bytes = MAX_PREFLIGHT_OUTPUT_BYTES
    if timeout_seconds is None:
        timeout_seconds = PREFLIGHT_TIMEOUT_SECONDS
    process_group = os.name == "posix"
    popen_options: dict[str, Any] = {
        "env": dict(environment),
        "cwd": cwd,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
    }
    if process_group:
        popen_options["start_new_session"] = True
    try:
        try:
            process = subprocess.Popen(list(command), **popen_options)
        except (TypeError, ValueError, NotImplementedError):
            popen_options.pop("start_new_session", None)
            process_group = False
            process = subprocess.Popen(list(command), **popen_options)
    except OSError as exc:
        raise LifecycleError(f"could not start {label}: {exc}") from exc
    assert process.stdout is not None and process.stderr is not None
    for stream in (process.stdout, process.stderr):
        try:
            os.set_blocking(stream.fileno(), False)
        except (AttributeError, OSError):
            # selectors still provide the portable readiness boundary on
            # platforms without os.set_blocking().
            pass
    streams = {process.stdout: bytearray(), process.stderr: bytearray()}
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    selector.register(process.stderr, selectors.EVENT_READ)
    started = time.monotonic()
    try:
        while selector.get_map():
            remaining = timeout_seconds - (time.monotonic() - started)
            if remaining <= 0:
                _terminate_subprocess(process, process_group=process_group)
                raise LifecycleError(f"{label} timed out after {timeout_seconds} seconds")
            events = selector.select(timeout=min(remaining, 1.0))
            for key, _mask in events:
                stream = key.fileobj
                try:
                    chunk = os.read(stream.fileno(), 65_536)
                except BlockingIOError:
                    continue
                if not chunk:
                    selector.unregister(stream)
                    continue
                output = streams[stream]
                output.extend(chunk)
                if len(output) > max_bytes:
                    _terminate_subprocess(process, process_group=process_group)
                    raise LifecycleError(
                        f"{label} output exceeds the {max_bytes}-byte safety limit"
                    )
        remaining = timeout_seconds - (time.monotonic() - started)
        if remaining <= 0:
            _terminate_subprocess(process, process_group=process_group)
            raise LifecycleError(f"{label} timed out after {timeout_seconds} seconds")
        try:
            return_code = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired as exc:
            _terminate_subprocess(process, process_group=process_group)
            raise LifecycleError(
                f"{label} timed out after {timeout_seconds} seconds"
            ) from exc
    finally:
        selector.close()
        process.stdout.close()
        process.stderr.close()
        if process.poll() is None:  # pragma: no cover - exceptional interpreter path
            _terminate_subprocess(process, process_group=process_group)
    return return_code, bytes(streams[process.stdout]), bytes(streams[process.stderr])


def _terminate_subprocess(process: subprocess.Popen[bytes], *, process_group: bool) -> None:
    """Terminate the capture process tree where supported and always reap parent."""

    group_killed = False
    if process_group and hasattr(os, "killpg"):
        try:
            os.killpg(process.pid, signal.SIGKILL)
            group_killed = True
        except (OSError, ValueError):
            group_killed = False
    if process.poll() is None and not group_killed:
        try:
            process.kill()
        except OSError:
            pass
    try:
        process.wait()
    except OSError:
        pass


def _cplt_probe_command(
    launch_command: Sequence[str],
    *,
    config: Path,
    preflight_project: Path,
    client_arguments: Sequence[str],
    additional_read: Path | None = None,
) -> list[str]:
    command = list(launch_command)
    try:
        delimiter = command.index("--")
        read_index = command.index("--allow-read") + 1
        project_index = command.index("--project-dir") + 1
    except ValueError as exc:  # pragma: no cover - internal command invariant
        raise LifecycleError("internal cplt command is missing probe boundaries") from exc
    command[read_index] = str(config)
    command[project_index] = str(preflight_project)
    prefix = [
        argument
        for argument in command[:delimiter]
        if argument not in {"--no-quiet", "--no-audit"}
    ]
    if additional_read is not None:
        prefix.extend(["--allow-read", str(additional_read)])
    return [
        *prefix,
        "--quiet",
        "--no-audit",
        "--",
        *client_arguments,
    ]


def _run_cplt_json_probe(
    launch_command: Sequence[str],
    *,
    config: Path,
    preflight_project: Path,
    client_arguments: Sequence[str],
    environment: Mapping[str, str],
    label: str,
    additional_read: Path | None = None,
    config_content_override: str | None = None,
) -> bytes:
    probe_environment = dict(environment)
    probe_environment["OPENCODE_CONFIG_DIR"] = str(config)
    if config_content_override is not None:
        probe_environment["OPENCODE_CONFIG_CONTENT"] = config_content_override
    command = _cplt_probe_command(
        launch_command,
        config=config,
        preflight_project=preflight_project,
        client_arguments=client_arguments,
        additional_read=additional_read,
    )
    _recheck_managed_command_executables(command, probe_environment)
    return_code, stdout, stderr = _bounded_subprocess_output(
        command, environment=probe_environment, label=label
    )
    if return_code != 0:
        raise LifecycleError(
            f"{label} failed with exit code {return_code}; captured output is "
            "suppressed because resolved OpenCode config may contain credentials"
        )
    bounded_single_write_probe = tuple(client_arguments) in {
        ("debug", "config"),
        ("debug", "skill"),
    } or tuple(client_arguments[:2]) == ("debug", "agent")
    if bounded_single_write_probe and len(stdout) >= PINNED_BUN_PIPE_FLUSH_BOUNDARY:
        raise LifecycleError(
            "sandboxed OpenCode debug output reached the pinned OpenCode/Bun "
            "64 KiB piped-stdout truncation boundary"
        )
    if bounded_single_write_probe and len(stdout) > PINNED_BUN_PIPE_SAFE_OUTPUT_BUDGET:
        raise LifecycleError(
            "sandboxed OpenCode debug output exceeded the managed 48 KiB "
            "piped-stdout safety budget"
        )
    return stdout


def _run_cplt_missing_agent_probe(
    launch_command: Sequence[str],
    *,
    config: Path,
    preflight_project: Path,
    agent_id: str,
    environment: Mapping[str, str],
) -> str:
    """Prove one disabled native/generated agent is absent from Agent.state."""

    probe_environment = dict(environment)
    probe_environment["OPENCODE_CONFIG_DIR"] = str(config)
    command = _cplt_probe_command(
        launch_command,
        config=config,
        preflight_project=preflight_project,
        client_arguments=("debug", "agent", agent_id),
    )
    _recheck_managed_command_executables(command, probe_environment)
    returncode, stdout, stderr = _bounded_subprocess_output(
        command,
        environment=probe_environment,
        label=f"sandboxed disabled agent probe for {agent_id}",
    )
    combined = stdout + b"\n" + stderr
    if returncode == 0 or b"not found" not in combined.lower():
        raise LifecycleError(
            f"disabled OpenCode agent {agent_id!r} remained available at runtime"
        )
    return _sha256(combined)


def _opencode_client_arguments(
    runtime_agent: str, arguments: Sequence[str]
) -> list[str]:
    """Preserve profile-owned pure mode and place the selected runtime agent."""

    forwarded = list(arguments)
    if any(
        argument in {"--pure", "--no-pure"}
        or argument.startswith("--pure=")
        or argument.startswith("--no-pure=")
        for argument in forwarded
    ):
        raise LifecycleError(
            "OpenCode pure mode is controlled by the managed runtime profile; "
            "do not pass --pure or --no-pure"
        )
    if not forwarded:
        return ["--agent", runtime_agent]
    if forwarded[0] == "run":
        return ["run", "--agent", runtime_agent, *forwarded[1:]]
    if forwarded[0] in OPENCODE_COMMANDS:
        return forwarded
    return ["--agent", runtime_agent, *forwarded]


MANAGED_BLOCKED_OPENCODE_OPTIONS = frozenset(
    {
        "--agent",
        "--attach",
        "--auto",
        "--cors",
        "--dangerously-skip-permissions",
        "--dir",
        "--hostname",
        "--mdns",
        "--no-attach",
        "--no-auto",
        "--no-dangerously-skip-permissions",
        "--no-share",
        "--no-yolo",
        "--no-pure",
        "--port",
        "--prompt",
        "--pure",
        "--session",
        "--continue",
        "--fork",
        "--share",
        "--yolo",
    }
)


def _managed_option_name(argument: str) -> str:
    return argument.split("=", 1)[0]


def _validate_managed_opencode_arguments(
    arguments: Sequence[str], *, command_ids: Iterable[str]
) -> None:
    """Keep the pre-scanned cwd, agent and interactive ask contract immutable."""

    forwarded = list(arguments)
    for argument in forwarded:
        option = _managed_option_name(argument)
        if (
            option in MANAGED_BLOCKED_OPENCODE_OPTIONS
            or argument in {"-a", "-c", "-s"}
            or (
                argument.startswith(("-a", "-c", "-s"))
                and not argument.startswith("--")
            )
        ):
            raise LifecycleError(
                f"managed OpenCode launch forbids client option {option!r}"
            )

    if not forwarded:
        return
    if forwarded[:2] == ["agent", "list"] and len(forwarded) == 2:
        return
    if forwarded[0] == "models":
        if any(_managed_option_name(item) == "--refresh" for item in forwarded[1:]):
            raise LifecycleError("managed OpenCode models command forbids --refresh")
        return
    if forwarded[0] != "run":
        raise LifecycleError(
            "managed OpenCode supports no-argument TUI, run, exact 'agent list', "
            "or models; use native cplt for other OpenCode subcommands"
        )

    expected = set(command_ids)
    indexes = [
        index
        for index, value in enumerate(forwarded)
        if _managed_option_name(value) == "--command"
    ]
    if len(indexes) > 1:
        raise LifecycleError("managed OpenCode run accepts at most one --command")
    if indexes:
        index = indexes[0]
        argument = forwarded[index]
        if "=" in argument:
            command_id = argument.split("=", 1)[1]
        elif index + 1 < len(forwarded):
            command_id = forwarded[index + 1]
        else:
            raise LifecycleError("managed OpenCode --command requires a value")
        if command_id not in expected:
            raise LifecycleError(
                "managed OpenCode --command must name a generated Grillmester command"
            )


def launch(
    *,
    home: Path,
    runtime_root: Path,
    profile_id: str,
    local_ports: Sequence[int],
    provider_domains: Sequence[str],
    provider_ports: Sequence[int],
    private_provider_domains: Sequence[str],
    pass_environment: Sequence[str],
    auth_providers: Sequence[str],
    provider_ids: Sequence[str],
    provider_base_urls: Sequence[str],
    provider_models: Sequence[str],
    runtime_agent: str,
    direct: bool,
    cplt: str,
    opencode: str,
    opencode_arguments: Sequence[str],
    environment: Mapping[str, str],
) -> int:
    if not re.fullmatch(r"[a-z][a-z0-9-]*", runtime_agent):
        raise LifecycleError(f"invalid OpenCode agent ID: {runtime_agent!r}")
    home, runtime_root = _validate_lifecycle_locations(
        home, runtime_root, environment
    )
    auth_snapshot = "{}"
    if not direct:
        _require_audited_cplt_home(home)
    _, distribution = _active_distribution(home)
    inputs = _resolve_runtime_inputs(
        profile_id,
        local_ports,
        provider_domains,
        provider_ports,
        private_provider_domains,
        pass_environment,
        auth_providers,
        provider_ids,
        provider_base_urls,
        provider_models,
        environment,
        profile_root=distribution.root.joinpath(*PROFILE_RELATIVE.parts),
    )
    if direct and inputs.profile.cplt_policy == "local-only":
        raise LifecycleError(
            "direct OpenCode cannot enforce local-only networking; launch through cplt"
        )
    if direct and inputs.auth_providers:
        raise LifecycleError(
            "--auth-provider is a managed cplt credential filter; direct mode uses "
            "OpenCode's normal ambient auth handling"
        )
    if direct and inputs.provider_ids:
        raise LifecycleError(
            "--provider-id is a managed cplt provider filter; direct mode uses "
            "OpenCode's normal ambient provider handling"
        )
    project_root = _project_root(environment)
    instruction_paths: tuple[str, ...] = ()
    instruction_fingerprint: str | None = None
    cplt_configuration_snapshot: tuple[
        Mapping[str, Any] | None,
        str | None,
        Mapping[str, Any] | None,
    ] | None = None
    include_global_cplt_configuration = True
    if not direct:
        _validate_managed_environment_roots(
            project_root, home, runtime_root, environment
        )
        instruction_paths, instruction_fingerprint = _project_instruction_snapshot(
            project_root
        )
        include_global_cplt_configuration = (
            inputs.profile.cplt_policy != "local-only"
        )
        cplt_configuration_snapshot = _cplt_configuration_snapshot(
            project_root,
            environment,
            include_global=include_global_cplt_configuration,
        )
        if inputs.profile.cplt_policy == "local-only":
            _check_local_only_platform()
            _check_local_only_cplt_configuration(
                project_root,
                environment,
                protected_environment=inputs.pass_environment,
                instruction_paths=instruction_paths,
            )
        else:
            _check_cplt_stage_write_overlap(
                home,
                project_root,
                environment,
                protected_environment=inputs.pass_environment,
                instruction_paths=instruction_paths,
            )
        _require_cplt_configuration_unchanged(
            project_root,
            environment,
            cplt_configuration_snapshot,
            include_global=include_global_cplt_configuration,
        )
    child_environment = _runtime_environment(
        environment,
        inputs,
        direct=direct,
        project_root=project_root,
        home=home,
        runtime_root=runtime_root,
    )
    if not direct:
        # Auth.all() trusts OPENCODE_AUTH_CONTENT without schema validation.
        # Supply one exact sanitized snapshot so every probe and the final
        # launch see identical credentials and cannot fetch per-process remote
        # configuration through a ``wellknown`` entry.
        if inputs.auth_providers:
            auth_snapshot = _snapshot_opencode_auth(environment)
        # Version and baseline config probes need no provider credentials.
        # Keeping them empty also prevents unrelated ambient secrets from
        # reaching an OpenCode process before provider admission is proved.
        child_environment["OPENCODE_AUTH_CONTENT"] = "{}"
        child_environment["XDG_CONFIG_HOME"] = str(
            _resolved(
                Path(environment.get("XDG_CONFIG_HOME", ""))
                if environment.get("XDG_CONFIG_HOME")
                else _account_home() / ".config"
            )
        )
    executable_resolution_environment = {
        "PATH": environment.get("PATH", os.defpath)
    }
    permission_composer: types.ModuleType | None = None
    extension_fingerprint: str | None = None
    extension_scan_environment: Mapping[str, str] | None = None
    if not direct:
        # OpenCode 1.18.20 imports auto-discovered plugin modules before its
        # permission policy can help. Reject the surface before any OpenCode
        # subprocess, then load only manifest-pinned composition code.
        extension_fingerprint = _scan_managed_opencode_extensions(
            project_root, child_environment
        )
        extension_scan_environment = dict(child_environment)
        permission_composer = _load_verified_permission_composer(distribution)

    resolved_opencode = _resolve_executable(
        opencode, label="OpenCode", environment=executable_resolution_environment
    )
    resolved_cplt_source: str | None = None
    if direct:
        # `--direct` is an explicit trusted-code opt-out from cplt isolation.
        _check_exact_client_version(
            resolved_opencode,
            label="OpenCode",
            expected_output=SUPPORTED_OPENCODE_VERSION,
            environment=child_environment,
        )
    else:
        _require_managed_cplt_libc()
        if _is_within(Path(resolved_opencode), project_root):
            raise LifecycleError(
                "cplt-managed OpenCode executable must not be inside its writable "
                "project directory"
            )
        cplt_opencode = _resolve_executable(
            "opencode",
            label="cplt-selected OpenCode",
            environment=executable_resolution_environment,
        )
        if not _same_path(Path(cplt_opencode), Path(resolved_opencode)):
            raise LifecycleError(
                "--opencode must resolve to the same executable that cplt selects from PATH"
            )
        resolved_cplt_source = _resolve_executable(
            cplt, label="cplt", environment=executable_resolution_environment
        )
    _ensure_owned_directory(runtime_root, label="OpenCode runtime root")
    sessions = runtime_root / "sessions"
    _ensure_owned_directory(sessions, label="OpenCode runtime sessions")
    session = Path(
        tempfile.mkdtemp(prefix=f"{distribution.release_id[:12]}-", dir=sessions)
    )
    config = session / "config"
    policy = session / "policy"
    try:
        isolated_config_home: Path | None = None
        isolated_test_home: Path | None = None
        isolated_test_home_identity: tuple[int, int] | None = None
        isolated_config_support_files: dict[PurePosixPath, str] | None = None
        isolated_config_support_fingerprint: str | None = None
        if not direct:
            for name, relative in (
                ("XDG_CACHE_HOME", "xdg-cache"),
                ("XDG_DATA_HOME", "xdg-data"),
                ("XDG_STATE_HOME", "xdg-state"),
            ):
                isolated = session / relative
                isolated.mkdir(mode=0o700)
                child_environment[name] = str(isolated)
            isolated_config_home = session / "xdg-config"
            isolated_config_home.mkdir(mode=0o700)
            isolated_opencode_config = isolated_config_home / "opencode"
            isolated_opencode_config.mkdir(mode=0o700)
            isolated_config_support_files = _stage_opencode_runtime_support(
                isolated_opencode_config
            )
            isolated_opencode_config.chmod(0o500)
            isolated_config_home.chmod(0o500)
            isolated_test_home = session / "opencode-home"
            isolated_test_home.mkdir(mode=0o700)
            isolated_test_home.chmod(0o500)
            isolated_test_home_identity = _validate_sealed_empty_directory(
                isolated_test_home, label="isolated OpenCode home"
            )
            child_environment["OPENCODE_TEST_HOME"] = str(isolated_test_home)
            isolated_config_support_fingerprint = _validate_staged_config_extras(
                isolated_opencode_config, isolated_config_support_files
            )
        _copy_bundle(distribution.target, config, immutable=False)
        staged = verify_bundle(config, immutable=False)
        if staged.release_id != distribution.target.release_id:  # pragma: no cover
            raise LifecycleError("runtime target ID changed while copying")
        runtime_support_files = _stage_opencode_runtime_support(config)
        if direct:
            _seal_composed_runtime_config(
                config, distribution.target, runtime_support_files
            )
        policy.mkdir(mode=0o700)
        child_environment["OPENCODE_CONFIG_DIR"] = str(config)
        if not direct and inputs.profile.cplt_policy == "local-only":
            cplt_config = policy / "cplt-config.toml"
            _write_policy_file(cplt_config, [])
            child_environment["CPLT_CONFIG"] = str(cplt_config)
        arguments = list(opencode_arguments)
        if arguments and arguments[0] == "--":
            arguments.pop(0)
        client_arguments = _opencode_client_arguments(runtime_agent, arguments)
        if direct:
            command = [resolved_opencode, *client_arguments]
        else:
            assert resolved_cplt_source is not None
            staged_opencode = _stage_opencode_binary(
                Path(resolved_opencode), session
            )
            trusted_directory = Path(staged_opencode).parent
            child_environment["PATH"] = _managed_subprocess_path(
                trusted_directory,
                environment=environment,
                project_root=project_root,
                home=home,
                runtime_root=runtime_root,
            )
            selected_opencode = _resolve_executable(
                "opencode",
                label="privately staged OpenCode",
                environment=child_environment,
            )
            if not _same_path(Path(selected_opencode), Path(staged_opencode)):
                raise LifecycleError(
                    "cplt must select the privately staged OpenCode executable"
                )
            resolved_cplt = _stage_pinned_cplt_binary(
                Path(resolved_cplt_source), session
            )
            _seal_trusted_executable_directory(trusted_directory)
            _recheck_managed_command_executables(
                [resolved_cplt], child_environment
            )
            _check_exact_client_version(
                resolved_cplt,
                label="cplt",
                expected_output=f"cplt {SUPPORTED_CPLT_RELEASE}",
                environment=child_environment,
            )
            models_catalog = policy / "models.json"
            try:
                models_catalog.write_text("{}\n", encoding="utf-8")
                models_catalog.chmod(0o400)
            except OSError as exc:
                raise LifecycleError(
                    f"could not create isolated OpenCode model catalog: {exc}"
                ) from exc
            child_environment["OPENCODE_MODELS_PATH"] = str(models_catalog)
            assert isolated_test_home is not None
            command = _build_cplt_command(
                resolved_cplt,
                config,
                models_catalog,
                isolated_test_home,
                policy,
                project_root,
                inputs,
                client_arguments,
            )
            policy.chmod(0o500)
            preflight_project = session / "preflight-project"
            preflight_project.mkdir(mode=0o700)
            _check_opencode_version_inside_cplt(
                command,
                preflight_project=preflight_project,
                environment=child_environment,
            )
            assert permission_composer is not None
            assert extension_fingerprint is not None
            assert extension_scan_environment is not None
            if (
                _scan_managed_opencode_extensions(
                    project_root, extension_scan_environment
                )
                != extension_fingerprint
            ):
                raise LifecycleError(
                    "OpenCode config/plugin surface changed before permission preflight"
                )
            current_instruction_paths, current_instruction_fingerprint = (
                _project_instruction_snapshot(project_root)
            )
            if (
                current_instruction_paths != instruction_paths
                or current_instruction_fingerprint != instruction_fingerprint
            ):
                raise LifecycleError(
                    "project instruction chain changed before permission preflight"
                )
            staged_instruction_paths, staged_instruction_files = (
                _stage_project_instruction_snapshot(
                    project_root,
                    config,
                    expected_paths=instruction_paths,
                    expected_fingerprint=instruction_fingerprint,
                )
            )
            _check_effective_cplt_instruction_visibility(
                project_root,
                child_environment,
                staged_instruction_paths,
            )
            project_permission_overlays = _load_project_permission_overlays(
                project_root
            )
            empty_config = session / "permission-input"
            empty_config.mkdir(mode=0o700)
            empty_opencode = empty_config / "opencode.json"
            empty_opencode.write_text(
                '{"autoupdate":false,"share":"disabled"}\n', encoding="utf-8"
            )
            empty_opencode.chmod(0o400)
            _stage_opencode_runtime_support(empty_config)
            empty_config.chmod(0o500)
            baseline_config_home = session / "permission-xdg-config"
            try:
                baseline_config_home.mkdir(mode=0o700)
            except OSError as exc:
                raise LifecycleError(
                    "could not create resolved-config XDG snapshot home"
                ) from exc
            baseline_opencode_config = baseline_config_home / "opencode"
            baseline_config_files = _stage_ambient_xdg_config_snapshot(
                child_environment,
                baseline_opencode_config,
            )
            baseline_config_fingerprint = _validate_staged_config_extras(
                baseline_opencode_config,
                baseline_config_files,
            )
            try:
                baseline_config_home.chmod(0o500)
            except OSError as exc:
                raise LifecycleError(
                    "could not seal resolved-config XDG snapshot home"
                ) from exc
            if (
                _scan_managed_opencode_extensions(
                    project_root, extension_scan_environment
                )
                != extension_fingerprint
            ):
                raise LifecycleError(
                    "OpenCode config/plugin surface changed while staging the "
                    "resolved-config snapshot"
                )
            baseline_environment = dict(child_environment)
            baseline_environment["XDG_CONFIG_HOME"] = str(baseline_config_home)
            baseline_output = _run_cplt_json_probe(
                command,
                config=empty_config,
                preflight_project=preflight_project,
                client_arguments=("debug", "config"),
                environment=baseline_environment,
                label="sandboxed baseline OpenCode config probe",
                # OPENCODE_CONFIG_DIR is additive in pinned OpenCode. Resolve
                # the three pre-scanned ambient config files from a sealed,
                # manager-owned XDG snapshot instead of granting cplt access to
                # an arbitrary custom XDG parent outside its normal home reads.
                additional_read=baseline_config_home,
            )
            if (
                _validate_staged_config_extras(
                    baseline_opencode_config,
                    baseline_config_files,
                )
                != baseline_config_fingerprint
            ):
                raise LifecycleError(
                    "ambient OpenCode XDG config snapshot changed during probe"
                )
            resolved_config = _composer_call(
                permission_composer, "parse_resolved_config", baseline_output
            )
            _composer_call(
                permission_composer,
                "require_no_external_extensions",
                resolved_config,
            )
            resolved_config = _select_resolved_providers(
                resolved_config,
                inputs=inputs,
                environment=environment,
            )
            assert isolated_config_home is not None
            assert isolated_config_support_files is not None
            assert isolated_config_support_fingerprint is not None
            if (
                _validate_staged_config_extras(
                    isolated_config_home / "opencode",
                    isolated_config_support_files,
                )
                != isolated_config_support_fingerprint
            ):
                raise LifecycleError(
                    "isolated OpenCode config support changed before composition"
                )
            child_environment["XDG_CONFIG_HOME"] = str(isolated_config_home)
            child_environment["OPENCODE_AUTH_CONTENT"] = (
                _select_opencode_auth_for_resolved_providers(
                    auth_snapshot,
                    resolved_config,
                    inputs.auth_providers,
                )
            )
            composed = _composer_call(
                permission_composer,
                "compose_policy",
                config,
                resolved_config,
                project_permission_overlays,
                staged_instruction_paths,
                runtime_agent,
            )
            config_probe_content = _composer_call(
                permission_composer,
                "build_bounded_config_probe_content",
                composed,
            )
            public_agents = tuple(
                sorted(
                    agent_id
                    for agent_id, contract in composed.agent_contracts.items()
                    if contract.get("mode") == "primary"
                    and contract.get("hidden") is False
                )
            )
            if runtime_agent not in public_agents:
                raise LifecycleError(
                    f"managed OpenCode agent must be one of: "
                    f"{', '.join(public_agents)}"
                )
            _validate_managed_opencode_arguments(
                arguments, command_ids=composed.command_contracts
            )
            _composer_call(
                permission_composer, "rewrite_staged_agents", config, composed
            )
            sealed_config_extras = {
                **runtime_support_files,
                **staged_instruction_files,
            }
            config_probe_inventory = frozenset(
                {
                    *(entry.relative for entry in distribution.target.entries),
                    *sealed_config_extras,
                }
            )
            _seal_composed_runtime_config(
                config,
                distribution.target,
                sealed_config_extras,
            )
            config_probe = session / "config-probe"
            (
                config_probe_source_files,
                config_probe_files,
                config_probe_fingerprint,
            ) = _stage_bounded_config_probe(
                config,
                config_probe,
                expected_inventory=config_probe_inventory,
            )
            if (
                _validate_config_probe_projection(
                    config,
                    config_probe,
                    expected_inventory=config_probe_inventory,
                    expected_source_files=config_probe_source_files,
                    expected_probe_files=config_probe_files,
                )
                != config_probe_fingerprint
            ):  # pragma: no cover - identical freshly sealed inputs
                raise LifecycleError("bounded config probe fingerprint drifted")
            staged_config_extra_fingerprint = _validate_staged_config_extras(
                config, sealed_config_extras
            )
            child_environment["OPENCODE_CONFIG_CONTENT"] = composed.config_content

            first_digests = _validate_composed_opencode_session(
                permission_composer,
                composed,
                command,
                config=config,
                config_probe=config_probe,
                preflight_project=preflight_project,
                config_probe_content=config_probe_content,
                environment=child_environment,
            )
            if (
                _scan_managed_opencode_extensions(
                    project_root, extension_scan_environment
                )
                != extension_fingerprint
            ):
                raise LifecycleError(
                    "OpenCode config/plugin surface changed during permission preflight"
                )
            if _project_instruction_snapshot(project_root) != (
                instruction_paths,
                instruction_fingerprint,
            ):
                raise LifecycleError(
                    "project instruction chain changed during permission preflight"
                )
            if (
                _validate_staged_config_extras(
                    config, sealed_config_extras
                )
                != staged_config_extra_fingerprint
            ):
                raise LifecycleError(
                    "staged config extras changed during permission preflight"
                )
            if (
                _validate_staged_config_extras(
                    isolated_config_home / "opencode",
                    isolated_config_support_files,
                )
                != isolated_config_support_fingerprint
            ):
                raise LifecycleError(
                    "isolated OpenCode config support changed during permission "
                    "preflight"
                )
            if (
                _validate_config_probe_projection(
                    config,
                    config_probe,
                    expected_inventory=config_probe_inventory,
                    expected_source_files=config_probe_source_files,
                    expected_probe_files=config_probe_files,
                )
                != config_probe_fingerprint
            ):
                raise LifecycleError(
                    "bounded OpenCode config probe changed during permission preflight"
                )
            second_digests = _validate_composed_opencode_session(
                permission_composer,
                composed,
                command,
                config=config,
                config_probe=config_probe,
                preflight_project=preflight_project,
                config_probe_content=config_probe_content,
                environment=child_environment,
            )
            if first_digests != second_digests:
                raise LifecycleError(
                    "OpenCode effective permissions or skill origins changed "
                    "between identical same-stage preflights"
                )
            if (
                _scan_managed_opencode_extensions(
                    project_root, extension_scan_environment
                )
                != extension_fingerprint
            ):
                raise LifecycleError(
                    "OpenCode config/plugin surface changed before launch"
                )
            if _project_instruction_snapshot(project_root) != (
                instruction_paths,
                instruction_fingerprint,
            ):
                raise LifecycleError(
                    "project instruction chain changed before launch"
                )
            if (
                _validate_staged_config_extras(
                    config, sealed_config_extras
                )
                != staged_config_extra_fingerprint
            ):
                raise LifecycleError("staged config extras changed before launch")
            if (
                _validate_staged_config_extras(
                    isolated_config_home / "opencode",
                    isolated_config_support_files,
                )
                != isolated_config_support_fingerprint
            ):
                raise LifecycleError(
                    "isolated OpenCode config support changed before launch"
                )
            if (
                _validate_config_probe_projection(
                    config,
                    config_probe,
                    expected_inventory=config_probe_inventory,
                    expected_source_files=config_probe_source_files,
                    expected_probe_files=config_probe_files,
                )
                != config_probe_fingerprint
            ):
                raise LifecycleError(
                    "bounded OpenCode config probe changed before launch"
                )
            assert isolated_test_home_identity is not None
            if _validate_sealed_empty_directory(
                isolated_test_home, label="isolated OpenCode home"
            ) != isolated_test_home_identity:
                raise LifecycleError("isolated OpenCode home changed before launch")
        try:
            if not direct:
                assert cplt_configuration_snapshot is not None
                _recheck_managed_command_executables(command, child_environment)
                _require_cplt_configuration_unchanged(
                    project_root,
                    environment,
                    cplt_configuration_snapshot,
                    include_global=include_global_cplt_configuration,
                )
                print(
                    "manage-opencode: permissions start fresh for this process; "
                    "choose 'Allow once'. OpenCode 'Always' and TUI auto-approve "
                    "are explicit process-wide relaxations; restart the manager "
                    "to clear approvals.",
                    file=sys.stderr,
                )
            result = subprocess.run(command, env=child_environment, check=False)
        except OSError as exc:
            client = "OpenCode" if direct else "cplt"
            raise LifecycleError(f"could not launch {client}: {exc}") from exc
        return result.returncode
    finally:
        _remove_private_tree(session)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Install, roll back and launch Grillmester's manifest-verified "
            "OpenCode target"
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    install_parser = subparsers.add_parser(
        "install", help="verify and activate an immutable generated target"
    )
    install_parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    install_parser.add_argument("--home", type=Path, default=None)

    rollback_parser = subparsers.add_parser(
        "rollback", help="atomically swap the active and previous release"
    )
    rollback_parser.add_argument("--home", type=Path, default=None)

    launch_parser = subparsers.add_parser(
        "launch", help="stage the active target and launch OpenCode"
    )
    launch_parser.add_argument("--home", type=Path, default=None)
    launch_parser.add_argument("--runtime-root", type=Path, default=None)
    launch_parser.add_argument(
        "--profile",
        choices=("local", "cloud-open-weight", "hybrid", "local-only"),
        default=None,
        help="required unless GRILLMESTER_OPENCODE_PROFILE is set",
    )
    launch_parser.add_argument("--local-port", type=int, action="append", default=[])
    launch_parser.add_argument(
        "--provider-domain", action="append", default=[], metavar="DOMAIN"
    )
    launch_parser.add_argument(
        "--provider-port", type=int, action="append", default=[], metavar="PORT"
    )
    launch_parser.add_argument(
        "--private-provider-domain", action="append", default=[], metavar="DOMAIN"
    )
    launch_parser.add_argument(
        "--pass-env", action="append", default=[], metavar="NAME"
    )
    launch_parser.add_argument(
        "--auth-provider",
        action="append",
        default=[],
        metavar="ID",
        help=(
            "admit one exact API entry from ambient auth.json after its custom "
            "provider config is validated; repeat as needed"
        ),
    )
    launch_parser.add_argument(
        "--provider-id",
        action="append",
        default=[],
        metavar="ID",
        help=(
            "admit one exact custom provider after binding its baseURL to the "
            "selected network profile; repeat as needed"
        ),
    )
    launch_parser.add_argument(
        "--provider-base-url",
        action="append",
        default=[],
        metavar="ID=URL",
        help=(
            "bind one selected provider to an exact launcher-owned base URL; "
            "required once for every --provider-id"
        ),
    )
    launch_parser.add_argument(
        "--provider-model",
        action="append",
        default=[],
        metavar="PROVIDER/MODEL",
        help=(
            "admit one exact model under a selected provider; repeat as needed"
        ),
    )
    launch_parser.add_argument("--runtime-agent", default="grillmester")
    launch_parser.add_argument(
        "--direct",
        action="store_true",
        help="run opencode directly; unavailable for the local-only profile",
    )
    launch_parser.add_argument(
        "--cplt", default="cplt", help="cplt executable pinned by this release"
    )
    launch_parser.add_argument(
        "--opencode",
        default="opencode",
        help=(
            "OpenCode executable pinned by this release; with cplt it must match "
            "the opencode selected from PATH"
        ),
    )
    launch_parser.add_argument(
        "opencode_arguments",
        nargs=argparse.REMAINDER,
        help="arguments after -- are forwarded to OpenCode",
    )
    return parser


def _require_isolated_python() -> None:
    """Require the stdlib-only bootstrap contract before managed lifecycle work."""

    if not sys.flags.isolated or not sys.flags.no_site:
        raise LifecycleError(
            "managed lifecycle commands require a trusted Python invoked with "
            "'-I -S'; native cplt and explicit --direct OpenCode are unaffected"
        )


def main(arguments: Sequence[str] | None = None) -> int:
    parser = _parser()
    invoked_as_script = arguments is None
    raw_arguments = list(arguments) if arguments is not None else sys.argv[1:]
    args = parser.parse_args(raw_arguments)
    try:
        if invoked_as_script and (
            args.command in {"install", "rollback"}
            or (args.command == "launch" and not args.direct)
        ):
            _require_isolated_python()
        if args.command == "install":
            home = args.home or default_home()
            release_id, changed = install(args.source, home)
            print(
                json.dumps(
                    {
                        "activeRelease": release_id,
                        "changed": changed,
                        "home": str(home.expanduser().absolute()),
                    },
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "rollback":
            home = args.home or default_home()
            _validate_lifecycle_locations(
                home, default_runtime_root(home), os.environ
            )
            _delegate_to_active_manager_if_needed(home, raw_arguments)
            release_id = rollback(home)
            print(
                json.dumps(
                    {
                        "activeRelease": release_id,
                        "home": str(home.expanduser().absolute()),
                    },
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "launch":
            profile_id = args.profile or os.environ.get(
                "GRILLMESTER_OPENCODE_PROFILE"
            )
            if not profile_id:
                raise LifecycleError(
                    "select --profile or set GRILLMESTER_OPENCODE_PROFILE"
                )
            home = args.home or default_home()
            runtime_root = args.runtime_root or default_runtime_root(home)
            _validate_lifecycle_locations(home, runtime_root, os.environ)
            _delegate_to_active_manager_if_needed(home, raw_arguments)
            return launch(
                home=home,
                runtime_root=runtime_root,
                profile_id=profile_id,
                local_ports=args.local_port,
                provider_domains=args.provider_domain,
                provider_ports=args.provider_port,
                private_provider_domains=args.private_provider_domain,
                pass_environment=args.pass_env,
                auth_providers=args.auth_provider,
                provider_ids=args.provider_id,
                provider_base_urls=args.provider_base_url,
                provider_models=args.provider_model,
                runtime_agent=args.runtime_agent,
                direct=args.direct,
                cplt=args.cplt,
                opencode=args.opencode,
                opencode_arguments=args.opencode_arguments,
                environment=os.environ,
            )
        parser.error(f"unsupported command: {args.command}")  # pragma: no cover
    except LifecycleError as exc:
        print(f"manage-opencode: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    return 2  # pragma: no cover


if __name__ == "__main__":
    raise SystemExit(main())
