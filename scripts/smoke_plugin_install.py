#!/usr/bin/env python3
"""Exercise the Grillmester plugin lifecycle in an isolated Copilot home."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, NamedTuple, Sequence


MARKETPLACE_NAME = "grillmester"
PLUGIN_REPOSITORY = "navikt/grillmester"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
SEMVER = re.compile(
    r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)
UNAVAILABLE_PLUGINS_COMMAND = "the plugins command is not available"
PREVIOUS_VERSION = "0.3.0-poc.1"
PREVIOUS_UNIFIED_VERSION = "0.3.0-rc.5"
UPGRADE_SENTINEL = ".grillmester-upgrade-fixture"
SAFE_ENV_PASSTHROUGH = {
    "PATH",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "NODE_EXTRA_CA_CERTS",
    "CURL_CA_BUNDLE",
    "REQUESTS_CA_BUNDLE",
}


class PackageSpec(NamedTuple):
    name: str
    path: str
    agents: int
    skills: int
    is_current_payload: bool

    @property
    def qualified_name(self) -> str:
        return f"{self.name}@{MARKETPLACE_NAME}"


PACKAGES = (
    PackageSpec("grillmester", "plugin", 7, 43, True),
)
LEGACY_CORE = PackageSpec("grillmester", "plugin", 7, 34, False)
LEGACY_ADD_ON = PackageSpec("grillmester-nav", "plugin-nav", 0, 10, False)
PREVIOUS_UNIFIED_PACKAGE = PackageSpec("grillmester", "plugin", 7, 43, False)
PREVIOUS_PACKAGES = (LEGACY_CORE, LEGACY_ADD_ON)
LEGACY_ADD_ON_SKILLS = (
    "grillmester-api-design",
    "grillmester-auth-overview",
    "grillmester-kafka-topic",
    "grillmester-kotlin-ktor",
    "grillmester-kotlin-spring",
    "grillmester-lumi-survey",
    "grillmester-nais-manifest",
    "grillmester-nav-troubleshoot",
    "grillmester-observability-setup",
    "grillmester-postgresql-review",
)
SAME_PACKAGE_REMOVED_SKILLS = ("grillmester-nav-architecture-review",)
HISTORICAL_REMOVED_SKILLS = ("grillmester-kotlin-spring",)
CURRENT_ONLY_SKILLS = ("grillmester-guided-review",)
REMOVED_SKILLS = SAME_PACKAGE_REMOVED_SKILLS + HISTORICAL_REMOVED_SKILLS
PACKAGE_BY_NAME = {package.name: package for package in PACKAGES}
PLUGIN_NAME = PACKAGES[0].name
PLUGIN_SPEC = PACKAGES[0].qualified_name
EXPECTED_AGENTS = PACKAGES[0].agents
EXPECTED_SKILLS = sum(package.skills for package in PACKAGES)


def isolated_cli_environment(
    base: dict[str, str],
    *,
    home: Path,
    copilot_home: Path,
    cache_home: Path,
    xdg_home: Path,
    temp_files: Path,
) -> dict[str, str]:
    """Build a minimal CLI environment without inheriting ambient credentials."""

    env = {key: value for key, value in base.items() if key in SAFE_ENV_PASSTHROUGH}
    env.update(
        {
            "CI": "true",
            "HOME": str(home),
            "COPILOT_HOME": str(copilot_home),
            "COPILOT_CACHE_HOME": str(cache_home),
            "COPILOT_AUTO_UPDATE": "false",
            "GIT_TERMINAL_PROMPT": "0",
            "GH_PROMPT_DISABLED": "1",
            "NO_COLOR": "1",
            "TERM": "dumb",
            "TMPDIR": str(temp_files),
            "XDG_CACHE_HOME": str(xdg_home / "cache"),
            "XDG_CONFIG_HOME": str(xdg_home / "config"),
            "XDG_DATA_HOME": str(xdg_home / "data"),
        }
    )
    return env


def execute(
    command: list[str], env: dict[str, str], cwd: Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def command_error(
    command: list[str], result: subprocess.CompletedProcess[str]
) -> RuntimeError:
    return RuntimeError(
        f"command failed with exit code {result.returncode}: "
        f"{shlex.join(command)}\n{result.stdout}"
    )


def run(command: list[str], env: dict[str, str], cwd: Path) -> str:
    result = execute(command, env, cwd)
    if result.returncode != 0:
        raise command_error(command, result)
    return result.stdout


def verify_local_cli_help_surface(
    copilot: str,
    env: dict[str, str],
    cwd: Path,
) -> None:
    """Require the minimum Copilot CLI to advertise every local-run option."""

    output = run([copilot, "--help"], env, cwd)
    advertised = set(
        re.findall(r"(?<![A-Za-z0-9-])--[A-Za-z0-9][A-Za-z0-9-]*", output)
    )
    for marker in (
        "--plugin-dir",
        "--agent",
        "--model",
        "--no-auto-update",
        "--no-experimental",
        "--no-remote",
        "--no-remote-export",
        "--disable-builtin-mcps",
        "--secret-env-vars",
        "--prompt",
        "--allow-all-tools",
        "--allow-all-paths",
        "--allow-all-urls",
        "--no-ask-user",
        "--deny-tool",
    ):
        if marker not in advertised:
            raise RuntimeError(
                f"Copilot CLI help omitted required local-run option {marker}"
            )


def load_json_object(path: Path, *, allow_comments: bool = False) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RuntimeError(f"required JSON file is missing: {path}") from exc
    if allow_comments:
        text = "\n".join(
            line for line in text.splitlines() if not line.lstrip().startswith("//")
        )
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"expected a JSON object in {path}")
    return value


def marketplace_sources_from_catalog(
    catalog_path: Path,
) -> dict[str, str | dict[str, Any]]:
    catalog = load_json_object(catalog_path)
    plugins = catalog.get("plugins")
    if not isinstance(plugins, list) or len(plugins) != len(PACKAGES):
        raise RuntimeError("marketplace catalog must contain exactly one Grillmester package")
    if any(not isinstance(entry, dict) for entry in plugins):
        raise RuntimeError("marketplace plugin entries must be objects")
    if [entry.get("name") for entry in plugins] != [p.name for p in PACKAGES]:
        raise RuntimeError("marketplace package names or order have drifted")
    result: dict[str, str | dict[str, Any]] = {}
    for entry in plugins:
        source = entry.get("source")
        if not isinstance(source, (str, dict)):
            raise RuntimeError("marketplace plugin source has an invalid type")
        result[entry["name"]] = source
    return result


def marketplace_source_from_catalog(catalog_path: Path) -> str | dict[str, Any]:
    """Return the canonical Grillmester package source."""

    return marketplace_sources_from_catalog(catalog_path)[PLUGIN_NAME]


def reviewed_release_tag(catalog_path: Path) -> str:
    """Derive the only valid remote marketplace tag from catalog metadata."""

    catalog = load_json_object(catalog_path)
    metadata = catalog.get("metadata")
    plugins = catalog.get("plugins")
    if not isinstance(metadata, dict) or not isinstance(plugins, list) or len(plugins) != 1:
        raise RuntimeError("marketplace catalog has no unambiguous release version")
    entry = plugins[0]
    version = entry.get("version") if isinstance(entry, dict) else None
    if not isinstance(version, str) or not is_strict_semver(version):
        raise RuntimeError("marketplace catalog version must be strict SemVer")
    if metadata.get("version") != version:
        raise RuntimeError("marketplace metadata and plugin versions differ")
    return f"v{version}"


def is_strict_semver(value: str) -> bool:
    """Validate the supported SemVer subset without ambiguous backtracking."""

    match = SEMVER.fullmatch(value)
    if match is None:
        return False
    prerelease = match.group(1)
    if prerelease is None:
        return True
    return all(
        identifier == "0"
        or not (identifier.isdigit() and identifier.startswith("0"))
        for identifier in prerelease.split(".")
    )


def marketplace_source(root: Path) -> str | dict[str, Any]:
    return marketplace_source_from_catalog(root / ".github/plugin/marketplace.json")


def plugin_version(plugin: Path) -> str:
    manifest = load_json_object(plugin / "plugin.json")
    version = manifest.get("version")
    if not isinstance(version, str) or not version.strip():
        raise RuntimeError(f"plugin manifest has no version: {plugin / 'plugin.json'}")
    return version


def write_json_object(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def add_removed_skill_fixtures(plugin: Path, skill_ids: Sequence[str]) -> None:
    """Add synthetic skills that existed only in an older package version."""

    for skill_id in skill_ids:
        removed_skill = plugin / "skills" / skill_id
        if removed_skill.exists():
            raise RuntimeError(
                f"removed skill is present in the current payload: {skill_id}"
            )
        removed_skill.mkdir(parents=True)
        (removed_skill / "SKILL.md").write_text(
            "---\n"
            f"name: {skill_id}\n"
            "description: Historical migration fixture; never ship this skill.\n"
            "---\n\n"
            "# Historical migration fixture\n",
            encoding="utf-8",
        )


def prepare_upgrade_marketplace(
    catalog_path: Path,
    source_root: Path,
    staged_marketplace: Path,
) -> tuple[
    dict[str, Path],
    dict[str, Any],
    Path,
    dict[str, Any],
    dict[str, Any],
]:
    """Create an older local source beside an exact current catalog fixture."""

    current_catalog = load_json_object(catalog_path)
    current_sources = marketplace_sources_from_catalog(catalog_path)
    current_versions = {
        plugin_version(source_root / package.path) for package in PACKAGES
    }
    if len(current_versions) != 1:
        raise RuntimeError("plugin manifest version is unavailable")
    current_version = next(iter(current_versions))
    if current_version in {PREVIOUS_VERSION, PREVIOUS_UNIFIED_VERSION}:
        raise RuntimeError("upgrade fixture versions must differ from the current plugin")

    plugins = current_catalog.get("plugins")
    if not isinstance(plugins, list) or len(plugins) != len(PACKAGES):
        raise RuntimeError("marketplace catalog must contain exactly one package")
    previous_plugins: dict[str, Path] = {}
    for package, current_entry in zip(PACKAGES, plugins, strict=True):
        if not isinstance(current_entry, dict) or current_entry.get("name") != package.name:
            raise RuntimeError("marketplace package roster has drifted")
        if current_entry.get("version") != current_version:
            raise RuntimeError("marketplace and package manifest versions do not match")
        source_package = source_root / package.path
        previous_path = f"previous-{package.path}"
        previous_plugin = staged_marketplace / previous_path
        shutil.copytree(source_package, previous_plugin)
        previous_manifest = load_json_object(previous_plugin / "plugin.json")
        previous_manifest["version"] = PREVIOUS_VERSION
        write_json_object(previous_plugin / "plugin.json", previous_manifest)
        (previous_plugin / UPGRADE_SENTINEL).write_text(
            "This file must disappear after a successful upgrade.\n",
            encoding="utf-8",
        )
        previous_plugins[package.name] = previous_plugin

        # Development sources resolve relative to the staged marketplace.
        if current_sources[package.name] == package.path:
            shutil.copytree(source_package, staged_marketplace / package.path)

    previous_core = previous_plugins[PLUGIN_NAME]
    for skill_id in CURRENT_ONLY_SKILLS:
        current_only_skill = previous_core / "skills" / skill_id
        if not current_only_skill.is_dir():
            raise RuntimeError(
                f"current-only skill is missing from current payload: {skill_id}"
            )
        shutil.rmtree(current_only_skill)
    add_removed_skill_fixtures(previous_core, SAME_PACKAGE_REMOVED_SKILLS)

    previous_unified_plugin = staged_marketplace / "previous-unified-plugin"
    shutil.copytree(previous_core, previous_unified_plugin)
    previous_unified_manifest = load_json_object(
        previous_unified_plugin / "plugin.json"
    )
    previous_unified_manifest["version"] = PREVIOUS_UNIFIED_VERSION
    write_json_object(
        previous_unified_plugin / "plugin.json", previous_unified_manifest
    )
    previous_unified_catalog = copy.deepcopy(current_catalog)
    previous_unified_catalog["metadata"]["version"] = PREVIOUS_UNIFIED_VERSION
    for entry in previous_unified_catalog["plugins"]:
        entry["version"] = PREVIOUS_UNIFIED_VERSION
        entry["source"] = "previous-unified-plugin"

    # The split poc.1 fixture predates the Spring removal as well as the
    # architecture-skill consolidation exercised from the rc.5 fixture.
    add_removed_skill_fixtures(previous_core, HISTORICAL_REMOVED_SKILLS)

    previous_add_on = staged_marketplace / f"previous-{LEGACY_ADD_ON.path}"
    (previous_add_on / "skills").mkdir(parents=True)
    for skill_id in LEGACY_ADD_ON_SKILLS:
        core_skill = previous_core / "skills" / skill_id
        if not core_skill.is_dir():
            raise RuntimeError(f"legacy add-on skill is missing from current payload: {skill_id}")
        shutil.copytree(core_skill, previous_add_on / "skills" / skill_id)
        shutil.rmtree(core_skill)
    for required in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(previous_core / required, previous_add_on / required)
    write_json_object(
        previous_add_on / "plugin.json",
        {
            "name": LEGACY_ADD_ON.name,
            "version": PREVIOUS_VERSION,
            "description": "Legacy Nav specialist skills retained only by migration smoke.",
            "author": {"name": "Team eSyfo"},
            "repository": "https://github.com/navikt/grillmester",
            "license": "MIT",
            "skills": "skills/",
        },
    )
    previous_plugins[LEGACY_ADD_ON.name] = previous_add_on

    previous_catalog = copy.deepcopy(current_catalog)
    previous_catalog["metadata"]["version"] = PREVIOUS_VERSION
    for package, entry in zip(PACKAGES, previous_catalog["plugins"], strict=True):
        entry["version"] = PREVIOUS_VERSION
        entry["source"] = f"previous-{package.path}"
    previous_catalog["plugins"].append(
        {
            "name": LEGACY_ADD_ON.name,
            "description": "Legacy Nav specialist skills retained only by migration smoke.",
            "version": PREVIOUS_VERSION,
            "source": f"previous-{LEGACY_ADD_ON.path}",
        }
    )
    return (
        previous_plugins,
        previous_catalog,
        previous_unified_plugin,
        previous_unified_catalog,
        current_catalog,
    )


def activate_marketplace_catalog(
    catalog: dict[str, Any],
    staged_marketplace: Path,
    copilot: str,
    env: dict[str, str],
    cwd: Path,
) -> None:
    write_json_object(
        staged_marketplace / ".github/plugin/marketplace.json",
        catalog,
    )
    run(
        [copilot, "plugin", "marketplace", "update", MARKETPLACE_NAME],
        env,
        cwd,
    )


def validate_catalog_sources(
    sources: dict[str, str | dict[str, Any]],
    *,
    expected_release_sha: str | None,
    checkout_sha: str,
) -> str | None:
    if set(sources) != set(PACKAGE_BY_NAME):
        raise RuntimeError("marketplace source package roster has drifted")
    development = all(
        sources[package.name] == package.path for package in PACKAGES
    )
    if development:
        if expected_release_sha is not None:
            raise RuntimeError("release smoke expected immutable GitHub sources")
        return None

    first_source = sources[PLUGIN_NAME]
    source_sha = first_source.get("sha") if isinstance(first_source, dict) else None
    if not isinstance(source_sha, str) or not FULL_SHA.fullmatch(source_sha):
        raise RuntimeError("release marketplace source needs one exact commit SHA")
    for package in PACKAGES:
        expected_source = {
            "source": "github",
            "repo": PLUGIN_REPOSITORY,
            "path": package.path,
            "sha": source_sha,
        }
        if sources[package.name] != expected_source:
            raise RuntimeError(
                "release marketplace has drifted from its pinned source shape"
            )
    if expected_release_sha is not None and source_sha != expected_release_sha:
        raise RuntimeError(
            f"release marketplace pins {source_sha}; expected {expected_release_sha}"
        )
    if source_sha != checkout_sha:
        raise RuntimeError(
            f"release marketplace pins {source_sha}; checkout HEAD is {checkout_sha}"
        )
    return source_sha


def validate_catalog_source(
    source: str | dict[str, Any],
    *,
    expected_release_sha: str | None,
    checkout_sha: str,
) -> str | None:
    """Compatibility helper for unit tests of a single canonical source."""

    sources = {PLUGIN_NAME: source}
    return validate_catalog_sources(
        sources,
        expected_release_sha=expected_release_sha,
        checkout_sha=checkout_sha,
    )


def tree_manifest(root: Path) -> dict[str, str]:
    if not root.is_dir():
        raise RuntimeError(f"plugin tree is missing: {root}")
    manifest: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise RuntimeError(f"plugin tree must not contain symlinks: {path}")
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            manifest[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not manifest:
        raise RuntimeError(f"plugin tree contains no files: {root}")
    return manifest


def assert_payload_matches(expected: Path, actual: Path) -> None:
    expected_files = tree_manifest(expected)
    actual_files = tree_manifest(actual)
    if expected_files == actual_files:
        return

    missing = sorted(expected_files.keys() - actual_files.keys())
    unexpected = sorted(actual_files.keys() - expected_files.keys())
    changed = sorted(
        path
        for path in expected_files.keys() & actual_files.keys()
        if expected_files[path] != actual_files[path]
    )
    details = []
    for label, paths in (
        ("missing", missing),
        ("unexpected", unexpected),
        ("changed", changed),
    ):
        if paths:
            details.append(f"{label}: {', '.join(paths[:5])}")
    raise RuntimeError("installed payload differs from source plugin; " + "; ".join(details))


def assert_removed_skills_absent(installed: Path) -> None:
    for skill_id in REMOVED_SKILLS:
        if (installed / "skills" / skill_id).exists():
            raise RuntimeError(
                f"current installation retained removed skill: {skill_id}"
            )


def assert_same_package_removed_skills_present(installed: Path) -> None:
    for skill_id in SAME_PACKAGE_REMOVED_SKILLS:
        if not (installed / "skills" / skill_id).is_dir():
            raise RuntimeError(
                f"same-package update fixture is missing removed skill: {skill_id}"
            )
    for skill_id in HISTORICAL_REMOVED_SKILLS:
        if (installed / "skills" / skill_id).exists():
            raise RuntimeError(
                f"same-package update fixture unexpectedly contains older skill: {skill_id}"
            )


def verify_installed_package(
    source: Path, installed: Path, package: PackageSpec | None = None
) -> tuple[int, int]:
    package = package or PACKAGES[0]
    manifest_path = installed / "plugin.json"
    manifest = load_json_object(manifest_path)
    if manifest.get("name") != package.name:
        raise RuntimeError("installed plugin manifest has the wrong name")

    agent_count = len(list((installed / "agents").glob("*.agent.md")))
    skill_count = len(list((installed / "skills").glob("*/SKILL.md")))
    if agent_count != package.agents:
        raise RuntimeError(f"installed {agent_count} agents; expected {package.agents}")
    if skill_count != package.skills:
        raise RuntimeError(f"installed {skill_count} skills; expected {package.skills}")

    if package.is_current_payload:
        assert_removed_skills_absent(installed)

    for required in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        if not (installed / required).is_file():
            raise RuntimeError(f"installed plugin is missing {required}")

    assert_payload_matches(source, installed)
    return agent_count, skill_count


def enabled_setting(copilot_home: Path, plugin_spec: str = PLUGIN_SPEC) -> bool | None:
    settings = load_json_object(copilot_home / "settings.json")
    enabled = settings.get("enabledPlugins")
    if not isinstance(enabled, dict):
        raise RuntimeError("Copilot settings do not contain enabledPlugins")
    value = enabled.get(plugin_spec)
    if value is not None and not isinstance(value, bool):
        raise RuntimeError(f"{plugin_spec} enabledPlugins setting is not boolean")
    return value


def try_toggle_lifecycle(
    copilot: str,
    env: dict[str, str],
    cwd: Path,
    copilot_home: Path,
    package: PackageSpec | None = None,
) -> bool:
    package = package or PACKAGES[0]
    command_prefixes = ([copilot], [copilot, "--experimental"])
    disable_result: subprocess.CompletedProcess[str] | None = None
    selected_prefix: list[str] | None = None

    for prefix in command_prefixes:
        command = [*prefix, "plugins", "disable", package.qualified_name, "--plugin"]
        disable_result = execute(command, env, cwd)
        if disable_result.returncode == 0:
            selected_prefix = list(prefix)
            break
        if UNAVAILABLE_PLUGINS_COMMAND not in disable_result.stdout.lower():
            raise command_error(command, disable_result)

    if selected_prefix is None:
        assert disable_result is not None
        print(
            "SKIP enable/disable: this Copilot CLI exposes help for the plural "
            "plugins command, but does not expose the command itself."
        )
        return False

    if enabled_setting(copilot_home, package.qualified_name) is not False:
        raise RuntimeError("disable command did not persist disabled plugin state")
    disabled_listing = run([copilot, "plugin", "list"], env, cwd)
    if package.qualified_name not in disabled_listing or "[disabled]" not in disabled_listing:
        raise RuntimeError(f"plugin list did not report {package.name} as disabled")

    enable_command = [
        *selected_prefix,
        "plugins",
        "enable",
        package.qualified_name,
        "--plugin",
    ]
    run(enable_command, env, cwd)
    if enabled_setting(copilot_home, package.qualified_name) is not True:
        raise RuntimeError("enable command did not persist enabled plugin state")
    enabled_listing = run([copilot, "plugin", "list"], env, cwd)
    if package.qualified_name not in enabled_listing or "[disabled]" in enabled_listing:
        raise RuntimeError(f"plugin list did not report {package.name} as enabled")

    mode = "documented --experimental mode" if len(selected_prefix) > 1 else "default mode"
    print(f"Verified enable/disable lifecycle through {mode}.")
    return True


def verify_uninstalled(
    copilot_home: Path,
    installed: Path,
    package: PackageSpec | None = None,
) -> None:
    package = package or PACKAGES[0]
    if installed.exists():
        raise RuntimeError(f"uninstall left the plugin payload behind: {installed}")

    config = load_json_object(copilot_home / "config.json", allow_comments=True)
    installed_plugins = config.get("installedPlugins")
    if not isinstance(installed_plugins, list):
        raise RuntimeError("Copilot config does not contain installedPlugins")
    if any(
        isinstance(plugin, dict)
        and plugin.get("name") == package.name
        and plugin.get("marketplace") == MARKETPLACE_NAME
        for plugin in installed_plugins
    ):
        raise RuntimeError("uninstall left Grillmester in installedPlugins")

    settings = load_json_object(copilot_home / "settings.json")
    enabled = settings.get("enabledPlugins")
    if not isinstance(enabled, dict) or package.qualified_name in enabled:
        raise RuntimeError(f"uninstall left {package.name} in enabledPlugins")


def remote_install_smoke(
    *,
    copilot: str,
    env: dict[str, str],
    cwd: Path,
    copilot_home: Path,
    marketplace_ref: str,
    expected_tag: str,
    source_root: Path,
    allow_floating_marketplace: bool = False,
) -> tuple[int, int]:
    """Install from a real remote catalog ref, verify bytes, then uninstall."""

    if not marketplace_ref.startswith(f"{PLUGIN_REPOSITORY}#"):
        raise RuntimeError(
            f"remote marketplace ref must start with {PLUGIN_REPOSITORY}#"
        )
    actual_ref = marketplace_ref.removeprefix(f"{PLUGIN_REPOSITORY}#")
    allowed_refs = {expected_tag}
    if allow_floating_marketplace:
        allowed_refs.add("marketplace")
    if actual_ref not in allowed_refs:
        raise RuntimeError(
            f"remote marketplace ref must use reviewed release tag {expected_tag}"
            " or the explicitly allowed floating marketplace ref"
        )

    run(
        [copilot, "plugin", "marketplace", "add", marketplace_ref],
        env,
        cwd,
    )
    agent_count = 0
    skill_count = 0
    for package in PACKAGES:
        run([copilot, "plugin", "install", package.qualified_name], env, cwd)
        installed = copilot_home / "installed-plugins" / MARKETPLACE_NAME / package.name
        package_agents, package_skills = verify_installed_package(
            source_root / package.path, installed, package
        )
        agent_count += package_agents
        skill_count += package_skills
        if enabled_setting(copilot_home, package.qualified_name) is not True:
            raise RuntimeError(f"remote installation did not enable {package.name}")
    listing = run([copilot, "plugin", "list"], env, cwd)
    for package in PACKAGES:
        if package.qualified_name not in listing:
            raise RuntimeError(f"plugin list does not report {package.name}")

    for package in reversed(PACKAGES):
        installed = copilot_home / "installed-plugins" / MARKETPLACE_NAME / package.name
        run([copilot, "plugin", "uninstall", package.qualified_name], env, cwd)
        verify_uninstalled(copilot_home, installed, package)
    return agent_count, skill_count


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--expect-release-sha",
        help="require the marketplace to pin this exact GitHub commit",
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        help="catalog file to inspect instead of the checkout's development catalog",
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        help="source checkout containing the plugin payload",
    )
    parser.add_argument(
        "--source-sha",
        help="source checkout SHA when --source-root is outside this checkout",
    )
    parser.add_argument(
        "--remote-marketplace-ref",
        help=(
            "install from navikt/grillmester#v<version> in an isolated home "
            "instead of staging a local marketplace"
        ),
    )
    parser.add_argument(
        "--allow-floating-marketplace",
        action="store_true",
        help="allow the remote marketplace ref to be the floating marketplace branch",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.expect_release_sha is not None and not FULL_SHA.fullmatch(
        args.expect_release_sha
    ):
        print("--expect-release-sha must be a lowercase 40-character SHA", file=sys.stderr)
        return 2
    if args.allow_floating_marketplace and args.remote_marketplace_ref is None:
        print(
            "--allow-floating-marketplace requires --remote-marketplace-ref",
            file=sys.stderr,
        )
        return 2

    copilot = shutil.which("copilot")
    if copilot is None:
        print("Copilot CLI is not installed.", file=sys.stderr)
        return 2

    root = Path(__file__).resolve().parents[1]
    source_root = args.source_root or root
    catalog_path = args.catalog or root / ".github/plugin/marketplace.json"
    checkout_sha = args.source_sha or run(
        ["git", "rev-parse", "HEAD"], os.environ.copy(), root
    ).strip()
    if FULL_SHA.fullmatch(checkout_sha) is None:
        print("--source-sha must be a lowercase 40-character SHA", file=sys.stderr)
        return 2
    release_sha = validate_catalog_sources(
        marketplace_sources_from_catalog(catalog_path),
        expected_release_sha=args.expect_release_sha,
        checkout_sha=checkout_sha,
    )
    if args.remote_marketplace_ref is not None and release_sha is None:
        raise RuntimeError("remote marketplace smoke requires a release catalog")
    expected_release_tag = reviewed_release_tag(catalog_path)

    with tempfile.TemporaryDirectory(prefix="grillmester-plugin-smoke-") as temp:
        temp_root = Path(temp)
        copilot_home = temp_root / "copilot-home"
        cache_home = temp_root / "copilot-cache"
        xdg_home = temp_root / "xdg"
        home = temp_root / "home"
        command_cwd = temp_root / "empty-worktree"
        temp_files = temp_root / "tmp"
        for path in (
            copilot_home,
            cache_home,
            xdg_home / "cache",
            xdg_home / "config",
            xdg_home / "data",
            home,
            command_cwd,
            temp_files,
        ):
            path.mkdir(parents=True)

        env = isolated_cli_environment(
            os.environ,
            home=home,
            copilot_home=copilot_home,
            cache_home=cache_home,
            xdg_home=xdg_home,
            temp_files=temp_files,
        )

        version_output = run([copilot, "--version"], env, command_cwd).strip()
        version = version_output.splitlines()[0]
        verify_local_cli_help_surface(
            copilot,
            env,
            command_cwd,
        )
        if args.remote_marketplace_ref is not None:
            agent_count, skill_count = remote_install_smoke(
                copilot=copilot,
                env=env,
                cwd=command_cwd,
                copilot_home=copilot_home,
                marketplace_ref=args.remote_marketplace_ref,
                expected_tag=expected_release_tag,
                source_root=source_root,
                allow_floating_marketplace=args.allow_floating_marketplace,
            )
            print(
                f"Verified remote catalog {args.remote_marketplace_ref} -> "
                f"{release_sha}: {agent_count} agents, {skill_count} skills, "
                f"byte-exact install and uninstall, and advertised local-run CLI surface "
                f"using {version}"
            )
            return 0

        staged_marketplace = temp_root / "marketplace"
        (
            previous_plugins,
            previous_catalog,
            previous_unified_plugin,
            previous_unified_catalog,
            current_catalog,
        ) = prepare_upgrade_marketplace(catalog_path, source_root, staged_marketplace)
        write_json_object(
            staged_marketplace / ".github/plugin/marketplace.json",
            previous_unified_catalog,
        )
        run(
            [copilot, "plugin", "marketplace", "add", str(staged_marketplace)],
            env,
            command_cwd,
        )
        run(
            [copilot, "plugin", "install", PREVIOUS_UNIFIED_PACKAGE.qualified_name],
            env,
            command_cwd,
        )
        unified_installed = (
            copilot_home
            / "installed-plugins"
            / MARKETPLACE_NAME
            / PREVIOUS_UNIFIED_PACKAGE.name
        )
        verify_installed_package(
            previous_unified_plugin,
            unified_installed,
            PREVIOUS_UNIFIED_PACKAGE,
        )
        assert_same_package_removed_skills_present(unified_installed)
        if enabled_setting(
            copilot_home, PREVIOUS_UNIFIED_PACKAGE.qualified_name
        ) is not True:
            raise RuntimeError("same-package fixture installation is not enabled")

        activate_marketplace_catalog(
            current_catalog,
            staged_marketplace,
            copilot,
            env,
            command_cwd,
        )
        run(
            [copilot, "plugin", "update", PACKAGES[0].qualified_name],
            env,
            command_cwd,
        )
        verify_installed_package(
            source_root / PACKAGES[0].path,
            unified_installed,
            PACKAGES[0],
        )
        if enabled_setting(copilot_home, PACKAGES[0].qualified_name) is not True:
            raise RuntimeError("same-package update did not preserve enabled state")

        activate_marketplace_catalog(
            previous_unified_catalog,
            staged_marketplace,
            copilot,
            env,
            command_cwd,
        )
        run(
            [copilot, "plugin", "uninstall", PACKAGES[0].qualified_name],
            env,
            command_cwd,
        )
        verify_uninstalled(copilot_home, unified_installed, PACKAGES[0])
        run(
            [copilot, "plugin", "install", PREVIOUS_UNIFIED_PACKAGE.qualified_name],
            env,
            command_cwd,
        )
        verify_installed_package(
            previous_unified_plugin,
            unified_installed,
            PREVIOUS_UNIFIED_PACKAGE,
        )
        assert_same_package_removed_skills_present(unified_installed)
        if enabled_setting(
            copilot_home, PREVIOUS_UNIFIED_PACKAGE.qualified_name
        ) is not True:
            raise RuntimeError("same-package rollback installation is not enabled")

        activate_marketplace_catalog(
            current_catalog,
            staged_marketplace,
            copilot,
            env,
            command_cwd,
        )
        run(
            [copilot, "plugin", "update", PACKAGES[0].qualified_name],
            env,
            command_cwd,
        )
        verify_installed_package(
            source_root / PACKAGES[0].path,
            unified_installed,
            PACKAGES[0],
        )
        if enabled_setting(copilot_home, PACKAGES[0].qualified_name) is not True:
            raise RuntimeError("same-package re-update did not preserve enabled state")

        run(
            [copilot, "plugin", "uninstall", PACKAGES[0].qualified_name],
            env,
            command_cwd,
        )
        verify_uninstalled(copilot_home, unified_installed, PACKAGES[0])
        activate_marketplace_catalog(
            previous_catalog,
            staged_marketplace,
            copilot,
            env,
            command_cwd,
        )
        for package in PREVIOUS_PACKAGES:
            run(
                [copilot, "plugin", "install", package.qualified_name],
                env,
                command_cwd,
            )
            installed = (
                copilot_home
                / "installed-plugins"
                / MARKETPLACE_NAME
                / package.name
            )
            verify_installed_package(
                previous_plugins[package.name], installed, package
            )
            if enabled_setting(copilot_home, package.qualified_name) is not True:
                raise RuntimeError(f"installation did not enable {package.name}")

        # Single-package consolidation requires explicit removal of the old
        # skills-only add-on before the marketplace roster loses that entry.
        legacy_installed = (
            copilot_home
            / "installed-plugins"
            / MARKETPLACE_NAME
            / LEGACY_ADD_ON.name
        )
        run(
            [copilot, "plugin", "uninstall", LEGACY_ADD_ON.qualified_name],
            env,
            command_cwd,
        )
        verify_uninstalled(copilot_home, legacy_installed, LEGACY_ADD_ON)

        activate_marketplace_catalog(
            current_catalog,
            staged_marketplace,
            copilot,
            env,
            command_cwd,
        )
        agent_count = 0
        skill_count = 0
        for package in PACKAGES:
            run(
                [copilot, "plugin", "update", package.qualified_name],
                env,
                command_cwd,
            )
            installed = (
                copilot_home / "installed-plugins" / MARKETPLACE_NAME / package.name
            )
            package_agents, package_skills = verify_installed_package(
                source_root / package.path, installed, package
            )
            agent_count += package_agents
            skill_count += package_skills
        verify_uninstalled(copilot_home, legacy_installed, LEGACY_ADD_ON)

        # `plugin update` only documents forward updates. Exercise rollback with
        # the documented uninstall/install path after repinning the marketplace.
        activate_marketplace_catalog(
            previous_catalog,
            staged_marketplace,
            copilot,
            env,
            command_cwd,
        )
        for package in reversed(PACKAGES):
            installed = (
                copilot_home / "installed-plugins" / MARKETPLACE_NAME / package.name
            )
            run(
                [copilot, "plugin", "uninstall", package.qualified_name],
                env,
                command_cwd,
            )
            verify_uninstalled(copilot_home, installed, package)
        for package in (LEGACY_CORE,):
            run(
                [copilot, "plugin", "install", package.qualified_name],
                env,
                command_cwd,
            )
            installed = (
                copilot_home / "installed-plugins" / MARKETPLACE_NAME / package.name
            )
            verify_installed_package(
                previous_plugins[package.name], installed, package
            )
            if enabled_setting(copilot_home, package.qualified_name) is not True:
                raise RuntimeError(f"rollback reinstall did not enable {package.name}")

        activate_marketplace_catalog(
            current_catalog,
            staged_marketplace,
            copilot,
            env,
            command_cwd,
        )
        for package in PACKAGES:
            installed = (
                copilot_home / "installed-plugins" / MARKETPLACE_NAME / package.name
            )
            run(
                [copilot, "plugin", "update", package.qualified_name],
                env,
                command_cwd,
            )
            verify_installed_package(source_root / package.path, installed, package)
            if enabled_setting(copilot_home, package.qualified_name) is not True:
                raise RuntimeError(
                    f"forward re-upgrade did not preserve {package.name} enabled state"
                )

        for package in PACKAGES:
            try_toggle_lifecycle(
                copilot, env, command_cwd, copilot_home, package
            )
            installed = (
                copilot_home / "installed-plugins" / MARKETPLACE_NAME / package.name
            )
            run(
                [copilot, "plugin", "update", package.qualified_name],
                env,
                command_cwd,
            )
            verify_installed_package(source_root / package.path, installed, package)

        for package in reversed(PACKAGES):
            installed = (
                copilot_home / "installed-plugins" / MARKETPLACE_NAME / package.name
            )
            run(
                [copilot, "plugin", "uninstall", package.qualified_name],
                env,
                command_cwd,
            )
            verify_uninstalled(copilot_home, installed, package)
        final_listing = run([copilot, "plugin", "list"], env, command_cwd)
        for package in PACKAGES:
            if package.qualified_name in final_listing:
                raise RuntimeError(
                    f"plugin list still reports {package.name} after uninstall"
                )
        if LEGACY_ADD_ON.qualified_name in final_listing:
            raise RuntimeError("plugin list still reports the legacy add-on")
        verify_uninstalled(copilot_home, legacy_installed, LEGACY_ADD_ON)

        source_label = f"release {release_sha}" if release_sha else "development source"
        print(
            f"Verified {source_label}: {agent_count} agents, {skill_count} skills, "
            "same-package removed-skill cleanup and rollback, legacy add-on removal, "
            "byte-exact forward upgrade, explicit rollback, repeatable update, "
            f"advertised local-run CLI surface, and uninstall using {version}"
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(f"Plugin lifecycle smoke failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
