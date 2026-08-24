from __future__ import annotations

import importlib.util
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
    def test_formula_depends_on_cplt_and_never_packages_client_binaries(self) -> None:
        content = FORMULA.render_formula(
            tag="v1.2.3",
            bundle_name="grillmester-terminal-v1.2.3.tar.gz",
            bundle_sha256="e" * 64,
        )

        self.assertIn('depends_on "navikt/tap/cplt"', content)
        self.assertIn('depends_on "ripgrep"', content)
        self.assertNotIn('resource "grillmester-cplt"', content)
        self.assertNotIn('resource "grillmester-opencode"', content)
        self.assertNotIn("libexec/clients", content)
        self.assertNotIn("clients.install", content)

    def test_formula_binds_exact_release_and_documents_user_owned_clients(self) -> None:
        digest = "a" * 64
        content = FORMULA.render_formula(
            tag="v1.2.3-rc.4",
            bundle_name="grillmester-terminal-v1.2.3-rc.4.tar.gz",
            bundle_sha256=digest,
        )

        self.assertIn(
            "https://github.com/navikt/grillmester/releases/download/v1.2.3-rc.4/"
            "grillmester-terminal-v1.2.3-rc.4.tar.gz",
            content,
        )
        self.assertIn(f'sha256 "{digest}"', content)
        self.assertNotIn('version "1.2.3-rc.4"', content)
        self.assertIn('depends_on "navikt/tap/cplt"', content)
        self.assertNotIn('depends_on "opencode"', content)
        self.assertIn('depends_on "python@3.13"', content)
        self.assertIn('depends_on "ripgrep"', content)
        self.assertNotIn('resource "grillmester-cplt"', content)
        self.assertNotIn('resource "grillmester-opencode"', content)
        self.assertNotIn('export PATH="#{libexec}/clients:$PATH"', content)
        self.assertIn('cplt = formula_opt_bin("cplt")', content)
        self.assertIn('export PATH="#{cplt}:$PATH"', content)
        self.assertIn("#!/bin/sh", content)
        self.assertNotIn("#!/bin/bash", content)
        self.assertIn(
            'exec "#{python}" -I -S "#{libexec}/scripts/grillmester.py" "$@"',
            content,
        )
        self.assertIn('libexec.install Dir["*"]', content)
        self.assertIn("uses OpenCode and GitHub Copilot CLI from your PATH", content)
        self.assertIn("Homebrew launcher\n      never installs, replaces, or shadows", content)
        self.assertIn("Copilot app uses its own Plugins UI", content)

    def test_formula_has_no_architecture_specific_client_resources(self) -> None:
        content = FORMULA.render_formula(
            tag="v1.2.3",
            bundle_name="grillmester-terminal-v1.2.3.tar.gz",
            bundle_sha256="c" * 64,
        )

        self.assertNotIn("on_arm do", content)
        self.assertNotIn("on_intel do", content)
        self.assertNotIn("resource ", content)

    def test_formula_is_valid_ruby_syntax(self) -> None:
        content = FORMULA.render_formula(
            tag="v1.2.3",
            bundle_name="grillmester-terminal-v1.2.3.tar.gz",
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

    def test_launcher_shim_ignores_shell_and_python_startup_injection(self) -> None:
        content = FORMULA.render_formula(
            tag="v1.2.3",
            bundle_name="grillmester-terminal-v1.2.3.tar.gz",
            bundle_sha256="d" * 64,
        )
        start = content.index("      #!/bin/sh\n")
        end = content.index("    SH\n", start)
        shim = "\n".join(
            line[6:] for line in content[start:end].splitlines()
        ) + "\n"

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cplt = root / "cplt-bin"
            libexec = root / "libexec"
            scripts = libexec / "scripts"
            python_startup = root / "python-startup"
            cplt.mkdir()
            scripts.mkdir(parents=True)
            python_startup.mkdir()
            target = scripts / "grillmester.py"
            target.write_text("print('safe launcher')\n", encoding="utf-8")
            shell_marker = root / "shell-marker"
            python_marker = root / "python-marker"
            shell_hook = root / "shell-hook"
            shell_hook.write_text(
                f"touch {shell_marker}\n",
                encoding="utf-8",
            )
            (python_startup / "sitecustomize.py").write_text(
                "from pathlib import Path\n"
                f"Path({str(python_marker)!r}).write_text('executed')\n",
                encoding="utf-8",
            )
            launcher = root / "grillmester"
            launcher.write_text(
                shim.replace("#{cplt}", str(cplt))
                .replace("#{python}", sys.executable)
                .replace("#{libexec}", str(libexec)),
                encoding="utf-8",
            )
            launcher.chmod(0o700)
            environment = {
                **os.environ,
                "BASH_ENV": str(shell_hook),
                "PYTHONPATH": str(python_startup),
            }
            result = subprocess.run(
                [str(launcher)],
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
            shell_injected = shell_marker.exists()
            python_injected = python_marker.exists()

        self.assertEqual(0, result.returncode, result.stdout)
        self.assertEqual("safe launcher\n", result.stdout)
        self.assertFalse(shell_injected)
        self.assertFalse(python_injected)

    def test_generator_rejects_unbound_or_unsafe_inputs(self) -> None:
        cases = (
            ("latest", "grillmester-terminal-latest.tar.gz", "a" * 64),
            ("v1.2.3", "other-v1.2.3.tar.gz", "a" * 64),
            ("v1.2.3", "grillmester-terminal-v1.2.4.tar.gz", "a" * 64),
            ("v1.2.3", "grillmester-terminal-v1.2.3.tar.gz", "A" * 64),
        )
        for tag, name, digest in cases:
            with self.subTest(tag=tag, name=name), self.assertRaises(
                FORMULA.FormulaError
            ):
                FORMULA.render_formula(
                    tag=tag, bundle_name=name, bundle_sha256=digest
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
