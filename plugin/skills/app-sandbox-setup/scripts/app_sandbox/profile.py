"""Pure shell block rendering, validation and lossless merge."""

import json
import shlex
from pathlib import Path

from .paths import has_control

BEGIN = "# >>> app-sandbox-setup:toolchain v1 >>>"
END = "# <<< app-sandbox-setup:toolchain v1 <<<"
META = "# app-sandbox-setup:profile "


def safe_path(value):
    if not isinstance(value, str) or not Path(value).is_absolute() or has_control(value):
        raise ValueError("Invalid absolute path")
    return value


def target(home, shell, env, exists):
    kind = Path(shell).name
    if kind == "zsh":
        directory = env.get("ZDOTDIR") or str(home)
        return kind, Path(safe_path(directory)) / ".zprofile"
    if kind == "bash":
        for name in (".bash_profile", ".bash_login", ".profile"):
            if exists(home / name):
                return kind, home / name
        return kind, home / ".bash_profile"
    if kind == "fish":
        return kind, home / ".config/fish/conf.d/app-sandbox-setup.fish"
    return kind, None


def bounds(text):
    starts = text.count("# >>> app-sandbox-setup:toolchain")
    ends = text.count("# <<< app-sandbox-setup:toolchain")
    if not starts and not ends:
        return None
    if starts != 1 or ends != 1 or text.count(BEGIN) != 1 or text.count(END) != 1:
        raise ValueError("Malformed profile markers")
    start, end = text.index(BEGIN), text.index(END) + len(END)
    if text.index(END) < start + len(BEGIN):
        raise ValueError("Malformed profile markers")
    # Markers must be whole lines; never splice a user command.
    if (start and text[start - 1] != "\n") or (end < len(text) and text[end] != "\n"):
        raise ValueError("Malformed profile markers")
    return start, end


def block(config):
    kind = config["shell"]
    lines = [BEGIN, META + json.dumps(config, sort_keys=True, separators=(",", ":"))]
    if config.get("shims"):
        path = shlex.quote(safe_path(config["shims"]))
        if kind == "fish":
            lines += [f"if not contains -- {path} $PATH",
                      f"    set -gx PATH {path} $PATH", "end"]
        else:
            lines += [f'case ":$PATH:" in',
                      f'    *:{path}:*) ;;',
                      f'    *) export PATH={path}:"$PATH" ;;', "esac"]
    if config.get("java_home"):
        path = shlex.quote(safe_path(config["java_home"]))
        if kind == "fish":
            lines += ["if not set -q JAVA_HOME", f"    set -gx JAVA_HOME {path}", "end"]
        else:
            lines.append(f'[ -z "$JAVA_HOME" ] && export JAVA_HOME={path}')
    return "\n".join(lines + [END])


def config(text):
    span = bounds(text)
    if not span:
        return None
    owned = text[span[0]:span[1]]
    lines = owned.splitlines()
    try:
        value = json.loads(lines[1][len(META):]) if lines[1].startswith(META) else None
        if (not isinstance(value, dict)
                or set(value) != {"shell", "tools", "shims", "java_home", "readonly"}
                or value["shell"] not in ("zsh", "bash", "fish")
                or not isinstance(value["tools"], list)
                or not value["tools"]
                or any(item not in ("java", "node", "pnpm") for item in value["tools"])
                or not isinstance(value["readonly"], list)):
            raise ValueError()
        for path in value["readonly"]:
            safe_path(path)
        if block(value) != owned:
            raise ValueError()
        return value
    except (IndexError, TypeError, ValueError, KeyError):
        raise ValueError("Unrecognized managed profile block") from None


def merge(text, new):
    span = bounds(text)
    if span is None:
        return text + ("\n\n" if text and new else "") + new
    start, end = span
    if not new and end == len(text) and text[:start].endswith("\n\n"):
        start -= 2
    return text[:start] + new + text[end:]
