#!/usr/bin/env python3
"""Install the local Grillmester marketplace in an isolated Copilot home."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


PLUGIN_NAME = "grillmester"
EXPECTED_AGENTS = 8
EXPECTED_SKILLS = 43


def run(command: list[str], env: dict[str, str]) -> str:
    result = subprocess.run(
        command,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode != 0:
        rendered = " ".join(command)
        raise RuntimeError(
            f"command failed with exit code {result.returncode}: {rendered}\n"
            f"{result.stdout}"
        )
    return result.stdout


def main() -> int:
    copilot = shutil.which("copilot")
    if copilot is None:
        print("Copilot CLI is not installed.", file=sys.stderr)
        return 2

    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="grillmester-plugin-smoke-") as temp:
        temp_root = Path(temp)
        copilot_home = temp_root / "copilot-home"
        cache_home = temp_root / "copilot-cache"
        xdg_home = temp_root / "xdg"
        home = temp_root / "home"
        for path in (copilot_home, cache_home, xdg_home, home):
            path.mkdir(parents=True)

        env = os.environ.copy()
        env.update(
            {
                "HOME": str(home),
                "COPILOT_HOME": str(copilot_home),
                "COPILOT_CACHE_HOME": str(cache_home),
                "COPILOT_AUTO_UPDATE": "false",
                "XDG_CACHE_HOME": str(xdg_home / "cache"),
                "XDG_CONFIG_HOME": str(xdg_home / "config"),
                "XDG_DATA_HOME": str(xdg_home / "data"),
            }
        )

        version = run([copilot, "--version"], env).strip()
        run([copilot, "plugin", "marketplace", "add", str(root)], env)
        run(
            [copilot, "plugin", "install", f"{PLUGIN_NAME}@{PLUGIN_NAME}"],
            env,
        )

        installed = (
            copilot_home / "installed-plugins" / PLUGIN_NAME / PLUGIN_NAME
        )
        manifest_path = installed / "plugin.json"
        if not manifest_path.is_file():
            raise RuntimeError(f"installed plugin manifest is missing: {manifest_path}")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("name") != PLUGIN_NAME:
            raise RuntimeError("installed plugin manifest has the wrong name")

        agent_count = len(list((installed / "agents").glob("*.agent.md")))
        skill_count = len(list((installed / "skills").glob("*/SKILL.md")))
        if agent_count != EXPECTED_AGENTS:
            raise RuntimeError(
                f"installed {agent_count} agents; expected {EXPECTED_AGENTS}"
            )
        if skill_count != EXPECTED_SKILLS:
            raise RuntimeError(
                f"installed {skill_count} skills; expected {EXPECTED_SKILLS}"
            )

        for required in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
            if not (installed / required).is_file():
                raise RuntimeError(f"installed plugin is missing {required}")

        print(
            f"Installed {PLUGIN_NAME} with {agent_count} agents and "
            f"{skill_count} skills using {version}."
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(f"Plugin install smoke failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
