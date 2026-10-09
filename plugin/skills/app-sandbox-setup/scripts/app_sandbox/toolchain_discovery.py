"""Read-only toolchain observations; subprocess boundaries are injectable."""

import os
import re
import shutil
import json
import shlex
import subprocess
import sys
from pathlib import Path

from . import toolchain
from .paths import has_control


SYSTEM_JDK_ROOT = Path("/Library/Java/JavaVirtualMachines")


def session_environment(home, env=None, runner=None):
    """Capture only allowed toolchain fields, never return arbitrary shell output."""
    env = os.environ if env is None else env
    runner = subprocess.run if runner is None else runner
    shell = env.get("SHELL", "")
    warning = "Session environment discovery failed; no profile activation."
    if Path(shell).name not in ("zsh", "bash", "fish") or not Path(shell).is_absolute() or has_control(shell):
        return None, warning
    keys = ("PATH", "JAVA_HOME", "MISE_DATA_DIR", "XDG_DATA_HOME",
            "ASDF_DATA_DIR", "SDKMAN_CANDIDATES_DIR")
    code = "import os,json; print(json.dumps({k:os.environ.get(k,'') for k in " + repr(keys) + "}))"
    clean = {key: env[key] for key in ("USER", "SHELL", "LANG", "ZDOTDIR", *keys[1:]) if env.get(key)}
    clean.update(HOME=str(home), TERM="dumb")
    try:
        result = runner([shell, "-l", "-i", "-c", shlex.quote(sys.executable) + " -c " + shlex.quote(code)],
                        stdin=subprocess.DEVNULL, cwd=str(home), env=clean,
                        capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            value = json.loads(result.stdout)
            if (isinstance(value, dict) and set(value) == set(keys)
                    and all(isinstance(item, str) and not has_control(item) for item in value.values())):
                return value, None
    except (OSError, subprocess.SubprocessError, ValueError, RecursionError):
        pass
    return None, warning


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


def jdks(home, env=None):
    env = os.environ if env is None else env
    mise = env.get("MISE_DATA_DIR") or (
        str(Path(env["XDG_DATA_HOME"]) / "mise") if env.get("XDG_DATA_HOME")
        else str(home / ".local/share/mise"))
    candidates = []
    for root, pattern in ((Path(mise) / "installs/java", "*"),
                          (home / "Library/Java/JavaVirtualMachines", "*/Contents/Home"),
                          (SYSTEM_JDK_ROOT, "*/Contents/Home"),
                          (Path(env.get("ASDF_DATA_DIR") or str(home / ".asdf")) / "installs/java", "*"),
                          (Path(env.get("SDKMAN_CANDIDATES_DIR") or str(home / ".sdkman/candidates")) / "java", "*")):
        if root.is_absolute() and not has_control(str(root)):
            candidates.extend(root.glob(pattern))
    if env.get("JAVA_HOME") and Path(env["JAVA_HOME"]).is_absolute():
        candidates.append(Path(env["JAVA_HOME"]))
    result = []
    for candidate in sorted(candidates, key=str, reverse=True):
        found = validated_jdk(candidate)
        if found and found not in result:
            result.append(found)
    return result


def validated_jdk(candidate):
    """Use the same release/bin validation as discovery; do not execute Java."""
    try:
        candidate = Path(candidate).resolve()
        if has_control(str(candidate)) or "`" in str(candidate):
            return None
        match = re.search(r'^JAVA_VERSION="([^"]+)"', (candidate / "release").read_text(encoding="utf-8"),
                          re.MULTILINE)
        version = toolchain.major(match[1]) if match else ""
        if version and (candidate / "bin/java").is_file() and os.access(str(candidate / "bin/java"), os.X_OK):
            return {"home": str(candidate), "major": version}
    except (OSError, UnicodeError, RuntimeError):
        pass
    return None


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
    gradle_pin = toolchain.detect({name: text for name, text in files.items()
                                  if name.endswith((".gradle", ".gradle.kts"))}).get("java")
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
    return {"pins": pins, "gradle_pin": gradle_pin, "gradlew": (repo / "gradlew").is_file(),
            "managers": managers(home), "jdks": jdks(home),
            "session_path": path, "session_warning": warning, "warnings": warnings,
            "repo_instructions": overlay,
            "resolved": {tool: shutil.which(tool, path=path) if path is not None else None
                         for tool in ("node", "pnpm")}}
