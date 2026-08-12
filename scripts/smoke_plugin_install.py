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
from typing import Any, Sequence


PLUGIN_NAME = "grillmester"
MARKETPLACE_NAME = "grillmester"
PLUGIN_SPEC = f"{PLUGIN_NAME}@{MARKETPLACE_NAME}"
PLUGIN_REPOSITORY = "navikt/grillmester"
EXPECTED_AGENTS = 7
EXPECTED_SKILLS = 44
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
UNAVAILABLE_PLUGINS_COMMAND = "the plugins command is not available"
PREVIOUS_VERSION = "0.0.0-upgrade-smoke"
PREVIOUS_SOURCE = "previous-plugin"
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


def marketplace_source_from_catalog(catalog_path: Path) -> str | dict[str, Any]:
    catalog = load_json_object(catalog_path)
    plugins = catalog.get("plugins")
    if not isinstance(plugins, list) or len(plugins) != 1:
        raise RuntimeError("marketplace catalog must contain exactly one plugin")
    entry = plugins[0]
    if not isinstance(entry, dict) or entry.get("name") != PLUGIN_NAME:
        raise RuntimeError("marketplace catalog does not contain Grillmester")
    source = entry.get("source")
    if not isinstance(source, (str, dict)):
        raise RuntimeError("marketplace plugin source has an invalid type")
    return source


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


def prepare_upgrade_marketplace(
    root: Path,
    source_plugin: Path,
    staged_marketplace: Path,
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    """Create an older local source beside an exact current catalog fixture."""

    current_catalog = load_json_object(root / ".github/plugin/marketplace.json")
    current_source = marketplace_source(root)
    current_version = plugin_version(source_plugin)
    if current_version == PREVIOUS_VERSION:
        raise RuntimeError("upgrade fixture version must differ from the current plugin")

    plugins = current_catalog.get("plugins")
    if not isinstance(plugins, list) or len(plugins) != 1:
        raise RuntimeError("marketplace catalog must contain exactly one plugin")
    current_entry = plugins[0]
    if not isinstance(current_entry, dict):
        raise RuntimeError("marketplace plugin entry must be an object")
    if current_entry.get("version") != current_version:
        raise RuntimeError("marketplace and plugin manifest versions do not match")

    previous_plugin = staged_marketplace / PREVIOUS_SOURCE
    shutil.copytree(source_plugin, previous_plugin)
    previous_manifest = load_json_object(previous_plugin / "plugin.json")
    previous_manifest["version"] = PREVIOUS_VERSION
    write_json_object(previous_plugin / "plugin.json", previous_manifest)
    (previous_plugin / UPGRADE_SENTINEL).write_text(
        "This file must disappear after a successful upgrade.\n",
        encoding="utf-8",
    )

    # A development catalog resolves its relative source from the registered
    # marketplace. Release catalogs keep their exact pinned GitHub source.
    if current_source == "plugin":
        shutil.copytree(source_plugin, staged_marketplace / "plugin")

    previous_catalog = copy.deepcopy(current_catalog)
    previous_catalog["metadata"]["version"] = PREVIOUS_VERSION
    previous_catalog["plugins"][0]["version"] = PREVIOUS_VERSION
    previous_catalog["plugins"][0]["source"] = PREVIOUS_SOURCE
    return previous_plugin, previous_catalog, current_catalog


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


def validate_catalog_source(
    source: str | dict[str, Any],
    *,
    expected_release_sha: str | None,
    checkout_sha: str,
) -> str | None:
    if source == "plugin":
        if expected_release_sha is not None:
            raise RuntimeError("release smoke expected an immutable GitHub source")
        return None
    if not isinstance(source, dict):
        raise RuntimeError("marketplace source must be 'plugin' or a GitHub object")

    source_sha = source.get("sha")
    if not isinstance(source_sha, str) or not FULL_SHA.fullmatch(source_sha):
        raise RuntimeError("release marketplace source needs an exact commit SHA")
    expected_source = {
        "source": "github",
        "repo": PLUGIN_REPOSITORY,
        "path": "plugin",
        "sha": source_sha,
    }
    if source != expected_source:
        raise RuntimeError("release marketplace source has drifted from the pinned shape")
    if expected_release_sha is not None and source_sha != expected_release_sha:
        raise RuntimeError(
            f"release marketplace pins {source_sha}; expected {expected_release_sha}"
        )
    if source_sha != checkout_sha:
        raise RuntimeError(
            f"release marketplace pins {source_sha}; checkout HEAD is {checkout_sha}"
        )
    return source_sha


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


def verify_installed_package(source: Path, installed: Path) -> tuple[int, int]:
    manifest_path = installed / "plugin.json"
    manifest = load_json_object(manifest_path)
    if manifest.get("name") != PLUGIN_NAME:
        raise RuntimeError("installed plugin manifest has the wrong name")

    agent_count = len(list((installed / "agents").glob("*.agent.md")))
    skill_count = len(list((installed / "skills").glob("*/SKILL.md")))
    if agent_count != EXPECTED_AGENTS:
        raise RuntimeError(f"installed {agent_count} agents; expected {EXPECTED_AGENTS}")
    if skill_count != EXPECTED_SKILLS:
        raise RuntimeError(f"installed {skill_count} skills; expected {EXPECTED_SKILLS}")

    for required in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        if not (installed / required).is_file():
            raise RuntimeError(f"installed plugin is missing {required}")

    assert_payload_matches(source, installed)
    return agent_count, skill_count


def enabled_setting(copilot_home: Path) -> bool | None:
    settings = load_json_object(copilot_home / "settings.json")
    enabled = settings.get("enabledPlugins")
    if not isinstance(enabled, dict):
        raise RuntimeError("Copilot settings do not contain enabledPlugins")
    value = enabled.get(PLUGIN_SPEC)
    if value is not None and not isinstance(value, bool):
        raise RuntimeError("Grillmester enabledPlugins setting is not boolean")
    return value


def try_toggle_lifecycle(
    copilot: str,
    env: dict[str, str],
    cwd: Path,
    copilot_home: Path,
) -> bool:
    command_prefixes = ([copilot], [copilot, "--experimental"])
    disable_result: subprocess.CompletedProcess[str] | None = None
    selected_prefix: list[str] | None = None

    for prefix in command_prefixes:
        command = [*prefix, "plugins", "disable", PLUGIN_SPEC, "--plugin"]
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

    if enabled_setting(copilot_home) is not False:
        raise RuntimeError("disable command did not persist disabled plugin state")
    disabled_listing = run([copilot, "plugin", "list"], env, cwd)
    if PLUGIN_SPEC not in disabled_listing or "[disabled]" not in disabled_listing:
        raise RuntimeError("stable plugin list did not report Grillmester as disabled")

    enable_command = [
        *selected_prefix,
        "plugins",
        "enable",
        PLUGIN_SPEC,
        "--plugin",
    ]
    run(enable_command, env, cwd)
    if enabled_setting(copilot_home) is not True:
        raise RuntimeError("enable command did not persist enabled plugin state")
    enabled_listing = run([copilot, "plugin", "list"], env, cwd)
    if PLUGIN_SPEC not in enabled_listing or "[disabled]" in enabled_listing:
        raise RuntimeError("stable plugin list did not report Grillmester as enabled")

    mode = "documented --experimental mode" if len(selected_prefix) > 1 else "default mode"
    print(f"Verified enable/disable lifecycle through {mode}.")
    return True


def verify_uninstalled(copilot_home: Path, installed: Path) -> None:
    if installed.exists():
        raise RuntimeError(f"uninstall left the plugin payload behind: {installed}")

    config = load_json_object(copilot_home / "config.json", allow_comments=True)
    installed_plugins = config.get("installedPlugins")
    if not isinstance(installed_plugins, list):
        raise RuntimeError("Copilot config does not contain installedPlugins")
    if any(
        isinstance(plugin, dict)
        and plugin.get("name") == PLUGIN_NAME
        and plugin.get("marketplace") == MARKETPLACE_NAME
        for plugin in installed_plugins
    ):
        raise RuntimeError("uninstall left Grillmester in installedPlugins")

    settings = load_json_object(copilot_home / "settings.json")
    enabled = settings.get("enabledPlugins")
    if not isinstance(enabled, dict) or PLUGIN_SPEC in enabled:
        raise RuntimeError("uninstall left Grillmester in enabledPlugins")


def remote_install_smoke(
    *,
    copilot: str,
    env: dict[str, str],
    cwd: Path,
    copilot_home: Path,
    marketplace_ref: str,
    source_plugin: Path,
) -> tuple[int, int]:
    """Install from a real remote catalog ref, verify bytes, then uninstall."""

    if not marketplace_ref.startswith(f"{PLUGIN_REPOSITORY}#"):
        raise RuntimeError(
            f"remote marketplace ref must start with {PLUGIN_REPOSITORY}#"
        )
    immutable_ref = marketplace_ref.removeprefix(f"{PLUGIN_REPOSITORY}#")
    if FULL_SHA.fullmatch(immutable_ref) is None:
        raise RuntimeError("pre-promotion remote smoke requires a full catalog SHA")

    run(
        [copilot, "plugin", "marketplace", "add", marketplace_ref],
        env,
        cwd,
    )
    run([copilot, "plugin", "install", PLUGIN_SPEC], env, cwd)
    installed = copilot_home / "installed-plugins" / MARKETPLACE_NAME / PLUGIN_NAME
    agent_count, skill_count = verify_installed_package(source_plugin, installed)
    if enabled_setting(copilot_home) is not True:
        raise RuntimeError("remote installation did not enable Grillmester")
    listing = run([copilot, "plugin", "list"], env, cwd)
    if PLUGIN_SPEC not in listing:
        raise RuntimeError("plugin list does not report the remote installation")

    run([copilot, "plugin", "uninstall", PLUGIN_SPEC], env, cwd)
    verify_uninstalled(copilot_home, installed)
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
        "--source-plugin",
        type=Path,
        help="plugin payload to compare with the installed package",
    )
    parser.add_argument(
        "--source-sha",
        help="source checkout SHA when --source-plugin is outside this checkout",
    )
    parser.add_argument(
        "--remote-marketplace-ref",
        help=(
            "install from navikt/grillmester#<catalog-SHA> in an isolated home "
            "instead of staging a local marketplace"
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.expect_release_sha is not None and not FULL_SHA.fullmatch(
        args.expect_release_sha
    ):
        print("--expect-release-sha must be a lowercase 40-character SHA", file=sys.stderr)
        return 2

    copilot = shutil.which("copilot")
    if copilot is None:
        print("Copilot CLI is not installed.", file=sys.stderr)
        return 2

    root = Path(__file__).resolve().parents[1]
    source_plugin = args.source_plugin or root / "plugin"
    catalog_path = args.catalog or root / ".github/plugin/marketplace.json"
    checkout_sha = args.source_sha or run(
        ["git", "rev-parse", "HEAD"], os.environ.copy(), root
    ).strip()
    if FULL_SHA.fullmatch(checkout_sha) is None:
        print("--source-sha must be a lowercase 40-character SHA", file=sys.stderr)
        return 2
    release_sha = validate_catalog_source(
        marketplace_source_from_catalog(catalog_path),
        expected_release_sha=args.expect_release_sha,
        checkout_sha=checkout_sha,
    )
    if args.remote_marketplace_ref is not None and release_sha is None:
        raise RuntimeError("remote marketplace smoke requires a release catalog")

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
        if args.remote_marketplace_ref is not None:
            agent_count, skill_count = remote_install_smoke(
                copilot=copilot,
                env=env,
                cwd=command_cwd,
                copilot_home=copilot_home,
                marketplace_ref=args.remote_marketplace_ref,
                source_plugin=source_plugin,
            )
            print(
                f"Verified remote catalog {args.remote_marketplace_ref} -> "
                f"{release_sha}: {agent_count} agents, {skill_count} skills, "
                f"byte-exact install and uninstall using {version}"
            )
            return 0

        staged_marketplace = temp_root / "marketplace"
        (
            previous_plugin,
            previous_catalog,
            current_catalog,
        ) = prepare_upgrade_marketplace(root, source_plugin, staged_marketplace)
        write_json_object(
            staged_marketplace / ".github/plugin/marketplace.json",
            previous_catalog,
        )
        run(
            [copilot, "plugin", "marketplace", "add", str(staged_marketplace)],
            env,
            command_cwd,
        )
        run(
            [copilot, "plugin", "install", PLUGIN_SPEC],
            env,
            command_cwd,
        )

        installed = (
            copilot_home / "installed-plugins" / MARKETPLACE_NAME / PLUGIN_NAME
        )
        verify_installed_package(previous_plugin, installed)
        if enabled_setting(copilot_home) is not True:
            raise RuntimeError("installation did not enable Grillmester")

        activate_marketplace_catalog(
            current_catalog,
            staged_marketplace,
            copilot,
            env,
            command_cwd,
        )
        run(
            [copilot, "plugin", "update", PLUGIN_SPEC],
            env,
            command_cwd,
        )
        agent_count, skill_count = verify_installed_package(source_plugin, installed)

        # `plugin update` only documents forward updates. Exercise rollback with
        # the documented uninstall/install path after repinning the marketplace.
        activate_marketplace_catalog(
            previous_catalog,
            staged_marketplace,
            copilot,
            env,
            command_cwd,
        )
        run(
            [copilot, "plugin", "uninstall", PLUGIN_SPEC],
            env,
            command_cwd,
        )
        verify_uninstalled(copilot_home, installed)
        run(
            [copilot, "plugin", "install", PLUGIN_SPEC],
            env,
            command_cwd,
        )
        verify_installed_package(previous_plugin, installed)
        if enabled_setting(copilot_home) is not True:
            raise RuntimeError("rollback reinstall did not enable Grillmester")

        activate_marketplace_catalog(
            current_catalog,
            staged_marketplace,
            copilot,
            env,
            command_cwd,
        )
        run(
            [copilot, "plugin", "update", PLUGIN_SPEC],
            env,
            command_cwd,
        )
        verify_installed_package(source_plugin, installed)
        if enabled_setting(copilot_home) is not True:
            raise RuntimeError("forward re-upgrade did not preserve enabled state")

        try_toggle_lifecycle(copilot, env, command_cwd, copilot_home)

        run(
            [copilot, "plugin", "update", PLUGIN_SPEC],
            env,
            command_cwd,
        )
        verify_installed_package(source_plugin, installed)

        run(
            [copilot, "plugin", "uninstall", PLUGIN_SPEC],
            env,
            command_cwd,
        )
        verify_uninstalled(copilot_home, installed)
        final_listing = run([copilot, "plugin", "list"], env, command_cwd)
        if PLUGIN_SPEC in final_listing:
            raise RuntimeError("plugin list still reports Grillmester after uninstall")

        source_label = f"release {release_sha}" if release_sha else "development source"
        print(
            f"Verified {source_label}: {agent_count} agents, {skill_count} skills, "
            "byte-exact forward upgrade, explicit rollback, repeatable update, "
            f"and uninstall using {version}"
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(f"Plugin lifecycle smoke failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
