#!/usr/bin/env python3
"""Generate the Homebrew formula for one immutable Grillmester release."""

from __future__ import annotations

import argparse
import json
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
BUNDLE_NAME = re.compile(r"^grillmester-opencode-v[0-9A-Za-z.-]+\.tar\.gz$")
DEFAULT_CLIENT_ARTIFACTS = (
    Path(__file__).resolve().parents[1] / "policy/client-artifacts.json"
)


class FormulaError(RuntimeError):
    """Raised when release metadata cannot produce a safe formula."""


def _macos_resources(path: Path) -> dict[str, dict[str, str]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FormulaError(f"could not read client artifact lock {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise FormulaError("client artifact lock must be a JSON object")

    resources: dict[str, dict[str, str]] = {}
    for architecture, brew_block in (("arm64", "on_arm"), ("x86_64", "on_intel")):
        selected: dict[str, str] = {"brew_block": brew_block}
        for client in ("cplt", "opencode"):
            client_lock = value.get(client)
            if not isinstance(client_lock, dict):
                raise FormulaError(f"client artifact lock has no {client} object")
            artifacts = client_lock.get("artifacts")
            if not isinstance(artifacts, list):
                raise FormulaError(f"client artifact lock has no {client} artifacts")
            matches = [
                artifact
                for artifact in artifacts
                if isinstance(artifact, dict)
                and artifact.get("platform") == "darwin"
                and artifact.get("architecture") == architecture
                and artifact.get("libc") == "none"
                and artifact.get("variant") == "default"
            ]
            if len(matches) != 1:
                raise FormulaError(
                    f"client artifact lock must select exactly one {client} "
                    f"artifact for macOS {architecture}"
                )
            artifact = matches[0]
            archive = artifact.get("archive")
            if not isinstance(archive, dict):
                raise FormulaError(f"{client} macOS {architecture} has no archive")
            url = artifact.get("url")
            digest = archive.get("sha256")
            if not isinstance(url, str) or not url.startswith("https://"):
                raise FormulaError(f"{client} macOS {architecture} has no HTTPS URL")
            if not isinstance(digest, str) or DIGEST.fullmatch(digest) is None:
                raise FormulaError(
                    f"{client} macOS {architecture} has no lowercase SHA-256"
                )
            selected[f"{client}_url"] = url
            selected[f"{client}_sha256"] = digest
        resources[architecture] = selected
    return resources


def render_formula(
    *,
    tag: str,
    bundle_name: str,
    bundle_sha256: str,
    client_artifacts: Path = DEFAULT_CLIENT_ARTIFACTS,
) -> str:
    if TAG.fullmatch(tag) is None:
        raise FormulaError("tag must be a strict v-prefixed SemVer")
    if BUNDLE_NAME.fullmatch(bundle_name) is None or bundle_name != (
        f"grillmester-opencode-{tag}.tar.gz"
    ):
        raise FormulaError("bundle name must be derived exactly from the release tag")
    if DIGEST.fullmatch(bundle_sha256) is None:
        raise FormulaError("bundle SHA-256 must be 64 lowercase hex characters")
    version = tag.removeprefix("v")
    url = (
        f"https://github.com/navikt/grillmester/releases/download/{tag}/"
        f"{bundle_name}"
    )
    resources = _macos_resources(client_artifacts)
    resource_blocks = []
    for architecture in ("arm64", "x86_64"):
        resource = resources[architecture]
        resource_blocks.append(
            f'''  {resource["brew_block"]} do
    resource "grillmester-cplt" do
      url "{resource["cplt_url"]}"
      sha256 "{resource["cplt_sha256"]}"
    end

    resource "grillmester-opencode" do
      url "{resource["opencode_url"]}"
      sha256 "{resource["opencode_sha256"]}"
    end
  end'''
        )
    rendered_resources = "\n\n".join(resource_blocks)
    return f'''class Grillmester < Formula
  desc "Agent team for software delivery, design, and product work in Nav"
  homepage "https://github.com/navikt/grillmester"
  url "{url}"
  version "{version}"
  sha256 "{bundle_sha256}"
  license "MIT"

  depends_on :macos
  depends_on "python@3.13"

{rendered_resources}

  def install
    libexec.install Dir["*"]
    clients = libexec/"clients"
    clients.mkpath
    resource("grillmester-cplt").stage do
      clients.install "cplt"
    end
    resource("grillmester-opencode").stage do
      clients.install "package/bin/opencode"
    end
    python = formula_opt_bin("python@3.13")/"python3.13"
    (bin/"grillmester").write <<~SH
      #!/bin/bash
      export PATH="#{{libexec}}/clients:$PATH"
      exec "#{{python}}" "#{{libexec}}/scripts/grillmester.py" "$@"
    SH
  end

  def caveats
    <<~EOS
      Run `grillmester` to choose GitHub Copilot CLI or OpenCode and one of the
      four public Grillmester agents. Both terminal clients run through cplt.

      This release includes the exact reviewed OpenCode and cplt binaries. To
      use GitHub Copilot CLI, install the separate client:
        brew install --cask copilot-cli

      Copilot app uses its own Plugins UI and is not started through Homebrew.
    EOS
  end

  test do
    assert_match "grillmester {version}", shell_output("#{{bin}}/grillmester --version")
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
    parser.add_argument(
        "--client-artifacts", type=Path, default=DEFAULT_CLIENT_ARTIFACTS
    )
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    options = parse_arguments(arguments)
    try:
        content = render_formula(
            tag=options.tag,
            bundle_name=options.bundle_name,
            bundle_sha256=options.bundle_sha256,
            client_artifacts=options.client_artifacts,
        )
        write_formula(options.output, content)
    except FormulaError as exc:
        print(f"Homebrew formula generation failed: {exc}", file=sys.stderr)
        return 2
    print(options.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
