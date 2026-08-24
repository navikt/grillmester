#!/usr/bin/env python3
"""Generate the Homebrew formula for one immutable Grillmester release."""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Sequence


TAG = re.compile(
    r"^v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
DIGEST = re.compile(r"^[0-9a-f]{64}$")
BUNDLE_NAME = re.compile(r"^grillmester-terminal-v[0-9A-Za-z.-]+\.tar\.gz$")


class FormulaError(RuntimeError):
    """Raised when release metadata cannot produce a safe formula."""


def render_formula(
    *,
    tag: str,
    bundle_name: str,
    bundle_sha256: str,
) -> str:
    if TAG.fullmatch(tag) is None:
        raise FormulaError("tag must be a strict v-prefixed SemVer")
    if BUNDLE_NAME.fullmatch(bundle_name) is None or bundle_name != (
        f"grillmester-terminal-{tag}.tar.gz"
    ):
        raise FormulaError("bundle name must be derived exactly from the release tag")
    if DIGEST.fullmatch(bundle_sha256) is None:
        raise FormulaError("bundle SHA-256 must be 64 lowercase hex characters")
    url = (
        f"https://github.com/navikt/grillmester/releases/download/{tag}/"
        f"{bundle_name}"
    )
    return f'''class Grillmester < Formula
  desc "Agent team for software delivery, design, and product work in Nav"
  homepage "https://github.com/navikt/grillmester"
  url "{url}"
  sha256 "{bundle_sha256}"
  license "MIT"

  depends_on :macos
  depends_on "navikt/tap/cplt"
  depends_on "python@3.13"
  depends_on "ripgrep"

  def install
    libexec.install Dir["*"]
    cplt = formula_opt_bin("cplt")
    python = formula_opt_bin("python@3.13")/"python3.13"
    (bin/"grillmester").write <<~SH
      #!/bin/sh
      export PATH="#{{cplt}}:$PATH"
      exec "#{{python}}" -I -S "#{{libexec}}/scripts/grillmester.py" "$@"
    SH
  end

  def caveats
    <<~EOS
      Run `grillmester` to choose GitHub Copilot CLI or OpenCode and one of the
      four public Grillmester agents. Both terminal clients run through cplt.

      Grillmester uses OpenCode and GitHub Copilot CLI from your PATH. Install
      and update the client or clients you want to use:
        brew install opencode
        brew install --cask copilot-cli

      cplt is installed as a required Homebrew dependency. The Homebrew launcher
      never installs, replaces, or shadows your OpenCode or GitHub Copilot CLI.

      Copilot app uses its own Plugins UI and is not started through Homebrew.
    EOS
  end

  test do
    assert_match "grillmester #{{version}}", shell_output("#{{bin}}/grillmester --version")
    assert_match "Launch Grillmester", shell_output("#{{bin}}/grillmester --help")
  end
end
'''


def write_formula(output: Path, content: str) -> None:
    output = output.expanduser().absolute()
    if output.is_symlink():
        raise FormulaError(f"refusing to replace symlinked output: {output}")
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                os.fchmod(stream.fileno(), 0o644)
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)
    except FormulaError:
        raise
    except OSError as exc:
        raise FormulaError(f"could not write formula {output}: {exc}") from exc


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--bundle-name", required=True)
    parser.add_argument("--bundle-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    options = parse_arguments(arguments)
    try:
        content = render_formula(
            tag=options.tag,
            bundle_name=options.bundle_name,
            bundle_sha256=options.bundle_sha256,
        )
        write_formula(options.output, content)
    except FormulaError as exc:
        print(f"Homebrew formula generation failed: {exc}", file=sys.stderr)
        return 2
    print(options.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
