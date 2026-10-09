#!/usr/bin/env python3
"""Plan and confirm portable GitHub Copilot desktop sandbox settings."""

from __future__ import annotations

import sys
from pathlib import Path

# Installed plugins are immutable payloads, including when loaded by importlib.
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app_sandbox.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
