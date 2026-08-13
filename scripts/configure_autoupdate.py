#!/usr/bin/env python3
"""Safely opt a user into Grillmester updates from the floating marketplace.

This script only updates the user-owned Copilot settings file. It deliberately
does not install or update a plugin, contact GitHub, or edit repository-managed
settings. Copilot CLI applies the configured update policy when a new trusted
CLI session starts.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import stat
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


MARKETPLACE_NAME = "grillmester"
PLUGIN_SPEC = "grillmester@grillmester"
EXPECTED_SOURCE = {
    "source": "github",
    "repo": "navikt/grillmester",
    "ref": "marketplace",
}
SAFE_FILE_MODE = 0o600
AUTO_UPDATE_ENVIRONMENT_VARIABLE = "COPILOT_AUTO_UPDATE"
AUTO_UPDATE_DISABLED_VALUE = "false"


class ConfigurationError(RuntimeError):
    """Raised when settings cannot be changed without risking user data."""


@dataclass(frozen=True)
class ConfigurationResult:
    settings_path: Path
    actions: tuple[str, ...]
    backup_path: Path | None = None
    dry_run: bool = False

    @property
    def changed(self) -> bool:
        return bool(self.actions)


def default_copilot_home() -> Path:
    configured = os.environ.get("COPILOT_HOME")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".copilot"


def environment_warnings(environment: Mapping[str, str]) -> tuple[str, ...]:
    """Report documented process overrides that make settings ineffective."""

    # GitHub documents the exact lowercase string "false". Do not infer that
    # other spellings or truthy/falsy conventions have the same CLI semantics.
    if (
        environment.get(AUTO_UPDATE_ENVIRONMENT_VARIABLE)
        != AUTO_UPDATE_DISABLED_VALUE
    ):
        return ()
    return (
        "COPILOT_AUTO_UPDATE=false disables Copilot's session-start "
        "auto-update path. settings.json can still be configured, but "
        "Grillmester will not update automatically in Copilot processes that "
        "inherit this environment variable. Unset COPILOT_AUTO_UPDATE before "
        "starting Copilot.",
    )


def _validate_existing_home(path: Path) -> None:
    try:
        home_stat = path.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise ConfigurationError(
            f"could not inspect Copilot home {path}: {exc}"
        ) from exc
    if stat.S_ISLNK(home_stat.st_mode):
        raise ConfigurationError(f"refusing to use symlinked Copilot home: {path}")
    if not stat.S_ISDIR(home_stat.st_mode):
        raise ConfigurationError(f"Copilot home is not a directory: {path}")
    if hasattr(os, "geteuid") and home_stat.st_uid != os.geteuid():
        raise ConfigurationError(f"Copilot home is not owned by this user: {path}")


def _load_settings(path: Path) -> tuple[dict[str, Any], bytes | None, int | None]:
    if path.is_symlink():
        raise ConfigurationError(
            f"refusing to replace symlinked settings file: {path}"
        )
    try:
        file_stat = path.stat()
    except FileNotFoundError:
        return {}, None, None
    except OSError as exc:
        raise ConfigurationError(f"could not inspect {path}: {exc}") from exc

    if not stat.S_ISREG(file_stat.st_mode):
        raise ConfigurationError(f"settings path is not a regular file: {path}")
    if hasattr(os, "geteuid") and file_stat.st_uid != os.geteuid():
        raise ConfigurationError(f"settings file is not owned by this user: {path}")

    try:
        original = path.read_bytes()
    except OSError as exc:
        raise ConfigurationError(f"could not read {path}: {exc}") from exc
    try:
        decoded = original.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ConfigurationError(f"settings file is not UTF-8: {path}") from exc
    try:
        value = json.loads(decoded)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(
            f"cannot safely update {path}: it is not strict JSON at "
            f"line {exc.lineno}, column {exc.colno}. JSONC comments and trailing "
            "commas are not rewritten; update this file manually or convert it "
            "to strict JSON first"
        ) from exc
    if not isinstance(value, dict):
        raise ConfigurationError(f"expected a JSON object in {path}")
    return value, original, stat.S_IMODE(file_stat.st_mode)


def _object_setting(settings: dict[str, Any], key: str) -> dict[str, Any]:
    value = settings.get(key)
    if value is None and key not in settings:
        value = {}
        settings[key] = value
    if not isinstance(value, dict):
        raise ConfigurationError(f"'{key}' must be a JSON object")
    return value


def merge_settings(
    current: dict[str, Any],
    *,
    replace_existing_marketplace: bool = False,
    enable_global_auto_update: bool = False,
) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Return the desired settings and a human-readable mutation plan."""

    merged = copy.deepcopy(current)
    actions: list[str] = []

    if "autoUpdate" in merged:
        global_auto_update = merged["autoUpdate"]
        if not isinstance(global_auto_update, bool):
            raise ConfigurationError("top-level 'autoUpdate' must be a JSON boolean")
        if global_auto_update is False:
            if not enable_global_auto_update:
                raise ConfigurationError(
                    "top-level 'autoUpdate' is explicitly false and disables "
                    "automatic updates for Copilot CLI itself and all plugins. "
                    "Refusing to override this user preference. Re-run with "
                    "--enable-global-auto-update only if you intend both effects"
                )
            merged["autoUpdate"] = True
            actions.append(
                "enable automatic updates for Copilot CLI itself and all plugins"
            )

    marketplaces = _object_setting(merged, "extraKnownMarketplaces")
    existing_marketplace = marketplaces.get(MARKETPLACE_NAME)
    if existing_marketplace is None and MARKETPLACE_NAME not in marketplaces:
        marketplace: dict[str, Any] = {
            "source": copy.deepcopy(EXPECTED_SOURCE),
            "autoUpdate": True,
        }
        marketplaces[MARKETPLACE_NAME] = marketplace
        actions.append("add the Grillmester marketplace on the floating channel")
    else:
        if not isinstance(existing_marketplace, dict):
            raise ConfigurationError(
                "'extraKnownMarketplaces.grillmester' must be a JSON object"
            )
        marketplace = existing_marketplace
        existing_source = marketplace.get("source")
        if existing_source != EXPECTED_SOURCE:
            if not replace_existing_marketplace:
                rendered = json.dumps(
                    existing_source, ensure_ascii=False, sort_keys=True
                )
                raise ConfigurationError(
                    "the existing Grillmester marketplace source is pinned or "
                    f"different ({rendered}). Refusing to overwrite it. Re-run "
                    "with --replace-existing-marketplace only if you intend to "
                    "switch to navikt/grillmester#marketplace"
                )
            marketplace["source"] = copy.deepcopy(EXPECTED_SOURCE)
            actions.append(
                "replace the existing Grillmester source with the floating "
                "marketplace channel"
            )
        if marketplace.get("autoUpdate") is not True:
            marketplace["autoUpdate"] = True
            actions.append("enable automatic Grillmester marketplace updates")

    enabled_plugins = _object_setting(merged, "enabledPlugins")
    if enabled_plugins.get(PLUGIN_SPEC) is not True:
        enabled_plugins[PLUGIN_SPEC] = True
        actions.append(f"enable {PLUGIN_SPEC}")

    return merged, tuple(actions)


def _create_backup(path: Path, original: bytes) -> Path:
    """Create a private, non-overwriting backup and return its path."""

    counter = 0
    while True:
        suffix = ".bak" if counter == 0 else f".bak.{counter}"
        candidate = path.with_name(path.name + suffix)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(candidate, flags, SAFE_FILE_MODE)
        except FileExistsError:
            counter += 1
            continue
        except OSError as exc:
            raise ConfigurationError(
                f"could not create backup {candidate}: {exc}"
            ) from exc

        try:
            os.fchmod(descriptor, SAFE_FILE_MODE)
            with os.fdopen(descriptor, "wb") as backup:
                descriptor = -1
                backup.write(original)
                backup.flush()
                os.fsync(backup.fileno())
        except OSError as exc:
            if descriptor >= 0:
                os.close(descriptor)
            try:
                candidate.unlink()
            except OSError:
                pass
            raise ConfigurationError(
                f"could not write backup {candidate}: {exc}"
            ) from exc
        return candidate


def _atomic_write(path: Path, content: bytes) -> None:
    descriptor = -1
    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        os.fchmod(descriptor, SAFE_FILE_MODE)
        with os.fdopen(descriptor, "wb") as target:
            descriptor = -1
            target.write(content)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
        try:
            directory_descriptor = os.open(path.parent, os.O_RDONLY)
        except OSError:
            directory_descriptor = -1
        if directory_descriptor >= 0:
            try:
                try:
                    os.fsync(directory_descriptor)
                except OSError:
                    # The settings file itself is already flushed and replaced.
                    # Some platforms do not support fsync on a directory.
                    pass
            finally:
                os.close(directory_descriptor)
    except OSError as exc:
        raise ConfigurationError(f"could not atomically update {path}: {exc}") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass


def configure(
    copilot_home: Path,
    *,
    dry_run: bool = False,
    replace_existing_marketplace: bool = False,
    enable_global_auto_update: bool = False,
) -> ConfigurationResult:
    home = copilot_home.expanduser()
    _validate_existing_home(home)
    settings_path = home / "settings.json"
    current, original, existing_mode = _load_settings(settings_path)
    merged, merge_actions = merge_settings(
        current,
        replace_existing_marketplace=replace_existing_marketplace,
        enable_global_auto_update=enable_global_auto_update,
    )
    actions = list(merge_actions)
    permission_change = original is not None and existing_mode != SAFE_FILE_MODE
    if permission_change:
        actions.append("restrict settings.json permissions to the current user")

    if dry_run or not actions:
        return ConfigurationResult(
            settings_path=settings_path,
            actions=tuple(actions),
            dry_run=dry_run,
        )

    try:
        home.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as exc:
        raise ConfigurationError(
            f"could not create Copilot home {home}: {exc}"
        ) from exc
    _validate_existing_home(home)

    backup_path = None
    content_changed = bool(merge_actions)
    if content_changed:
        if original is not None:
            backup_path = _create_backup(settings_path, original)
        encoded = (json.dumps(merged, ensure_ascii=False, indent=2) + "\n").encode(
            "utf-8"
        )
        _atomic_write(settings_path, encoded)
    elif permission_change:
        try:
            settings_path.chmod(SAFE_FILE_MODE)
        except OSError as exc:
            raise ConfigurationError(
                f"could not secure settings permissions for {settings_path}: {exc}"
            ) from exc

    return ConfigurationResult(
        settings_path=settings_path,
        actions=tuple(actions),
        backup_path=backup_path,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Configure user-owned Copilot settings for automatic Grillmester "
            "updates from navikt/grillmester#marketplace."
        )
    )
    parser.add_argument(
        "--copilot-home",
        type=Path,
        default=None,
        help=(
            "Copilot home containing settings.json "
            "(default: COPILOT_HOME or ~/.copilot)"
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the planned changes (the default is a read-only preview)",
    )
    parser.add_argument(
        "--replace-existing-marketplace",
        action="store_true",
        help=(
            "explicitly replace a pinned or different Grillmester marketplace "
            "source with navikt/grillmester#marketplace"
        ),
    )
    parser.add_argument(
        "--enable-global-auto-update",
        action="store_true",
        help=(
            "explicitly change top-level autoUpdate from false to true; this "
            "enables automatic updates for Copilot CLI itself and all plugins"
        ),
    )
    return parser


def _print_result(result: ConfigurationResult) -> None:
    if not result.changed:
        print(
            "Grillmester auto-update is already configured in "
            f"{result.settings_path}"
        )
        return
    verb = "Would update" if result.dry_run else "Updated"
    print(f"{verb} {result.settings_path}:")
    for action in result.actions:
        print(f"  - {action}")
    if result.backup_path is not None:
        print(f"Backup: {result.backup_path}")


def _print_warnings(warnings: Sequence[str]) -> None:
    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    _print_warnings(environment_warnings(os.environ))
    try:
        result = configure(
            arguments.copilot_home or default_copilot_home(),
            dry_run=not arguments.apply,
            replace_existing_marketplace=arguments.replace_existing_marketplace,
            enable_global_auto_update=arguments.enable_global_auto_update,
        )
    except ConfigurationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    _print_result(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
