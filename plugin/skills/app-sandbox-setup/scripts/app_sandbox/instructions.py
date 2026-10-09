"""Pure, deterministic managed block and lossless user-text merge."""

import re
import shlex
from pathlib import Path

from .paths import has_control
from .toolchain import command_prefix

BEGIN = "<!-- app-sandbox-setup:toolchain:begin v1 -->"
END = "<!-- app-sandbox-setup:toolchain:end -->"


def block(decisions):
    bullets = []
    for decision in decisions:
        if decision["command"]:
            pin = decision["pin"]
            prefix = command_prefix(decision)
            if decision["tool"] == "java":
                bullets.append(
                    f'- Java {pin["major"]} is pinned by {pin["source"]}; use '
                    f'`{prefix}./gradlew …` and `{prefix}java …`: '
                    'the macOS /usr/bin/java stub cannot find a JDK in the sandbox.'
                )
            else:
                tool = decision["tool"]
                bullets.append(f'- {tool} {pin["version"]} is pinned by {pin["source"]}; '
                               f'use `{prefix}{tool} …`: {tool} is missing from the session PATH.')
    if not bullets:
        return ""
    return "\n".join([BEGIN, "Toolchain in the sandbox (managed by /app-sandbox-setup)",
                      *bullets, "Do not change JAVA_HOME or install tools inside the sandbox.", END])


def bounds(text):
    starts = text.count("<!-- app-sandbox-setup:toolchain:begin")
    ends = text.count("<!-- app-sandbox-setup:toolchain:end")
    if not starts and not ends:
        return None
    if starts != 1 or ends != 1 or text.count(BEGIN) != 1 or text.count(END) != 1:
        raise ValueError("Malformed managed markers")
    start, end = text.index(BEGIN), text.index(END) + len(END)
    if text.index(END) < start + len(BEGIN):
        raise ValueError("Malformed managed markers")
    return start, end


def managed(text):
    span = bounds(text)
    return text[span[0]:span[1]] if span else ""


def display_block(text):
    """Only echo a canonical block, never arbitrary user edits inside markers."""
    owned = managed(text)
    if not owned:
        return ""
    sources = (".mise.toml", "mise.toml", ".tool-versions", ".java-version", ".sdkmanrc",
               ".nvmrc", ".node-version", "package.json", "build.gradle", "build.gradle.kts",
               "settings.gradle", "settings.gradle.kts")
    decisions = []
    for line in owned.splitlines()[2:-2]:
        java = re.fullmatch(r"- Java (\d+) is pinned by ([^;]+); use `(.*?)\./gradlew …` and "
                            r"`(.*?)java …`: the macOS /usr/bin/java stub cannot find a JDK in the sandbox.", line)
        frontend = re.fullmatch(r"- (node|pnpm) (\d+(?:\.\d+){0,2}) is pinned by ([^;]+); "
                                r"use `mise exec -- (node|pnpm) …`: (node|pnpm) is missing from the session PATH.", line)
        if java and java[2] in sources and java[3] == java[4]:
            command, home = "mise", None
            if java[3] != "mise exec -- ":
                try:
                    assignment = shlex.split(java[3])
                except ValueError:
                    break
                if len(assignment) != 1 or not assignment[0].startswith("JAVA_HOME="):
                    break
                home = assignment[0][len("JAVA_HOME="):]
                if not Path(home).is_absolute() or has_control(home) or "`" in home:
                    break
                command = "JAVA_HOME"
            decisions.append({"tool": "java", "command": command, "home": home,
                              "pin": {"major": java[1], "source": java[2]}})
        elif frontend and frontend[3] in sources and frontend[1] == frontend[4] == frontend[5]:
            decisions.append({"tool": frontend[1], "command": "mise",
                              "pin": {"version": frontend[2], "source": frontend[3]}})
        else:
            break
    if decisions and block(decisions) == owned:
        return owned
    return "(unrecognized managed block; contents not displayed)"


def merge(text, new_block):
    span = bounds(text)
    if span is None:
        return text + ("\n\n" if text and new_block else "") + new_block
    start, end = span
    if not new_block and end == len(text) and text[:start].endswith("\n\n"):
        start -= 2
    return text[:start] + new_block + text[end:]
