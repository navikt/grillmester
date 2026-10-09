"""Read-only toolchain observations; subprocess boundaries are injectable."""

import os
import re
import shutil
import subprocess
from pathlib import Path

from . import toolchain
from .paths import has_control


SYSTEM_JDK_ROOT = Path("/Library/Java/JavaVirtualMachines")


def managers(home, env=None):
    env = os.environ if env is None else env
    path = os.pathsep.join([env.get("PATH", ""), "/opt/homebrew/bin", "/usr/local/bin",
                            str(home / ".local/bin"), str(home / ".local/share/mise/bin")])
    return {"mise": shutil.which("mise", path=path),
            "asdf": shutil.which("asdf", path=path + os.pathsep + str(home / ".asdf/bin")) or (home / ".asdf").is_dir(),
            "sdkman": (home / ".sdkman").is_dir()}


def session_path(home, env=None, runner=None):
    env = os.environ if env is None else env
    runner = subprocess.run if runner is None else runner
    shell = env.get("SHELL")
    warning = "Session PATH discovery failed; node/pnpm unknown, no guidance."
    if not shell or not Path(shell).is_absolute() or has_control(shell):
        return None, warning
    clean = {key: env[key] for key in ("USER", "SHELL", "LANG") if key in env}
    clean.update(HOME=str(home), TERM="dumb")
    try:
        result = runner([shell, "-l", "-i", "-c", 'printf %s "$PATH"'],
                        stdin=subprocess.DEVNULL, cwd=str(home), env=clean,
                        capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and not has_control(result.stdout):
            return result.stdout, None
    except (OSError, subprocess.SubprocessError):
        pass
    return None, warning


def jdks(home):
    candidates = []
    for root, pattern in ((home / ".local/share/mise/installs/java", "*"),
                          (home / "Library/Java/JavaVirtualMachines", "*/Contents/Home"),
                          (SYSTEM_JDK_ROOT, "*/Contents/Home"),
                          (home / ".sdkman/candidates/java", "*")):
        candidates.extend(root.glob(pattern))
    result = []
    for candidate in sorted(candidates, key=str, reverse=True):
        try:
            match = re.search(r'^JAVA_VERSION="([^"]+)"', (candidate / "release").read_text(encoding="utf-8"),
                              re.MULTILINE)
            version = toolchain.major(match[1]) if match else ""
            if version and (candidate / "bin/java").is_file() and os.access(str(candidate / "bin/java"), os.X_OK):
                resolved = str(candidate.resolve())
                if not has_control(resolved) and "`" not in resolved:
                    result.append({"home": resolved, "major": version})
        except (OSError, UnicodeError, RuntimeError):
            continue
    return result


def observe(repo, home, capture_session=True):
    files = {}
    warnings = []
    for name in (".mise.toml", "mise.toml", ".tool-versions", ".java-version", ".sdkmanrc",
                 ".nvmrc", ".node-version", "package.json", "build.gradle", "build.gradle.kts",
                 "settings.gradle", "settings.gradle.kts"):
        try:
            files[name] = (repo / name).read_text(encoding="utf-8")
        except FileNotFoundError:
            pass
        except (OSError, UnicodeError):
            warnings.append("Toolchain file unavailable: " + name + "; contents are never printed.")
    pins = toolchain.detect(files)
    overlay = False
    try:
        text = (repo / ".github/github-app.yml").read_text(encoding="utf-8")
        overlay = bool(re.search(r"""^(?:instructions|"instructions"|'instructions')\s*:""", text, re.MULTILINE))
    except FileNotFoundError:
        pass
    except (OSError, UnicodeError):
        overlay = True
        warnings.append("Repo config unavailable; DB instructions left untouched.")
    path, warning = ((session_path(home) if any(tool in pins for tool in ("node", "pnpm")) else (None, None))
                     if capture_session else (os.environ.get("PATH", ""), None))
    return {"pins": pins, "managers": managers(home), "jdks": jdks(home),
            "session_path": path, "session_warning": warning, "warnings": warnings,
            "repo_instructions": overlay,
            "resolved": {tool: shutil.which(tool, path=path) if path is not None else None
                         for tool in ("node", "pnpm")}}
