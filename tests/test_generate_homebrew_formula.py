from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "grillmester_generate_homebrew_formula",
    ROOT / "scripts/generate_homebrew_formula.py",
)
assert SPEC is not None and SPEC.loader is not None
FORMULA = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = FORMULA
SPEC.loader.exec_module(FORMULA)


class GenerateHomebrewFormulaTests(unittest.TestCase):
    def test_formula_binds_exact_release_and_reviewed_terminal_clients(self) -> None:
        digest = "a" * 64
        content = FORMULA.render_formula(
            tag="v1.2.3-rc.4",
            bundle_name="grillmester-opencode-v1.2.3-rc.4.tar.gz",
            bundle_sha256=digest,
        )

        self.assertIn(
            "https://github.com/navikt/grillmester/releases/download/v1.2.3-rc.4/"
            "grillmester-opencode-v1.2.3-rc.4.tar.gz",
            content,
        )
        self.assertIn(f'sha256 "{digest}"', content)
        self.assertIn('version "1.2.3-rc.4"', content)
        self.assertNotIn('depends_on "navikt/tap/cplt"', content)
        self.assertNotIn('depends_on "opencode"', content)
        self.assertIn('depends_on "python@3.13"', content)
        self.assertIn('resource "grillmester-cplt"', content)
        self.assertIn('resource "grillmester-opencode"', content)
        self.assertIn(
            "cplt-aarch64-apple-darwin.tar.gz", content
        )
        self.assertIn(
            "opencode-darwin-arm64-1.18.20.tgz", content
        )
        self.assertIn(
            'export PATH="#{libexec}/clients:$PATH"', content
        )
        self.assertIn('clients.install "cplt"', content)
        self.assertIn('clients.install "package/bin/opencode"', content)
        self.assertIn('libexec.install Dir["*"]', content)
        self.assertIn("Copilot app uses its own Plugins UI", content)

    def test_formula_resources_cover_both_macos_architectures(self) -> None:
        content = FORMULA.render_formula(
            tag="v1.2.3",
            bundle_name="grillmester-opencode-v1.2.3.tar.gz",
            bundle_sha256="c" * 64,
        )

        self.assertIn("on_arm do", content)
        self.assertIn("on_intel do", content)
        for digest in (
            "fb1fd69f5ff42deb1cf2e510d97a58ff5f7ddf913e1cd4f7533815a16588eeda",
            "e60687724df8a2fdb6f99654cc80f1a0dccb215263c2d984c222ff99ce56f8ea",
            "5091c1188dc99026c066ae1e31451d6893409d807f14aca3f66928d1a44c55f7",
            "345a6684759fa78e2e9d11e3a8dd53bf7b963c60f303d8a7f8ca547999389104",
        ):
            with self.subTest(digest=digest):
                self.assertIn(f'sha256 "{digest}"', content)

    def test_formula_is_valid_ruby_syntax(self) -> None:
        content = FORMULA.render_formula(
            tag="v1.2.3",
            bundle_name="grillmester-opencode-v1.2.3.tar.gz",
            bundle_sha256="b" * 64,
        )
        with tempfile.TemporaryDirectory() as directory:
            formula = Path(directory) / "grillmester.rb"
            formula.write_text(content, encoding="utf-8")
            result = subprocess.run(
                ["ruby", "-c", str(formula)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertIn("Syntax OK", result.stdout)

    def test_generator_rejects_unbound_or_unsafe_inputs(self) -> None:
        cases = (
            ("latest", "grillmester-opencode-latest.tar.gz", "a" * 64),
            ("v1.2.3", "other-v1.2.3.tar.gz", "a" * 64),
            ("v1.2.3", "grillmester-opencode-v1.2.4.tar.gz", "a" * 64),
            ("v1.2.3", "grillmester-opencode-v1.2.3.tar.gz", "A" * 64),
        )
        for tag, name, digest in cases:
            with self.subTest(tag=tag, name=name), self.assertRaises(
                FORMULA.FormulaError
            ):
                FORMULA.render_formula(
                    tag=tag, bundle_name=name, bundle_sha256=digest
                )

    def test_generator_requires_reviewed_sha256_for_every_macos_resource(self) -> None:
        lock = json.loads(
            (ROOT / "policy/client-artifacts.json").read_text(encoding="utf-8")
        )
        lock["opencode"]["artifacts"][0]["archive"].pop("sha256")
        with tempfile.TemporaryDirectory() as directory:
            lock_path = Path(directory) / "client-artifacts.json"
            lock_path.write_text(json.dumps(lock), encoding="utf-8")
            with self.assertRaisesRegex(FORMULA.FormulaError, "has no lowercase SHA-256"):
                FORMULA.render_formula(
                    tag="v1.2.3",
                    bundle_name="grillmester-opencode-v1.2.3.tar.gz",
                    bundle_sha256="d" * 64,
                    client_artifacts=lock_path,
                )

    def test_output_is_private_from_symlink_replacement_and_mode_is_stable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "nested/grillmester.rb"
            FORMULA.write_formula(output, "class Grillmester < Formula\nend\n")
            self.assertEqual(0o644, stat.S_IMODE(output.stat().st_mode))

            target = root / "target.rb"
            target.write_text("do not replace\n", encoding="utf-8")
            link = root / "link.rb"
            link.symlink_to(target)
            with self.assertRaisesRegex(FORMULA.FormulaError, "symlinked output"):
                FORMULA.write_formula(link, "replacement\n")
            self.assertEqual("do not replace\n", target.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
