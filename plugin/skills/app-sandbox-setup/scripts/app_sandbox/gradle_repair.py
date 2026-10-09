"""Pure, lossless targeted Gradle paths merge; observations never run Gradle."""

import hashlib
import json
import os
import re
from pathlib import Path

from . import profile_store, store, toolchain_discovery
from .paths import SetupError, canonical, has_control

KEY = "org.gradle.java.installations.paths"
MARKER = "# app-sandbox-setup:gradle-toolchains "
NOTE = "This does NOT give the wrapper a java to start with. Per-project instructions handle that."


def auto_detected(path, home, env):
    candidate = Path(path).resolve()
    java_home = env.get("JAVA_HOME")
    if java_home and candidate == Path(java_home).resolve():
        return True
    roots = [Path(env.get("ASDF_DATA_DIR") or str(home / ".asdf")) / "installs/java",
             Path(env.get("SDKMAN_CANDIDATES_DIR") or str(home / ".sdkman/candidates")) / "java"]
    return any(candidate.parent == root.resolve() or any(
        child.resolve() == candidate for child in root.glob("*")) for root in roots)


def needed(connection, home, env):
    paths, evidence = [], []
    for row in store.project_rows(connection):
        raw = row["main_repo_path"]
        if not isinstance(raw, str) or not Path(raw).is_absolute() or has_control(raw):
            continue
        observation = toolchain_discovery.observe(Path(raw), home, capture_session=False)
        pin = observation.get("gradle_pin")
        matches = [jdk for jdk in observation["jdks"] if pin and jdk["major"] == pin["major"]]
        detected = any(auto_detected(jdk["home"], home, env) for jdk in matches)
        chosen = matches[0]["home"] if matches and not detected else None
        evidence.append({"id": row["id"], "pin": pin, "jdk": chosen, "detected": detected})
        if chosen:
            paths.append(chosen)
    return list(dict.fromkeys(paths)), evidence


def unescape(value):
    def replace(match):
        part = match[1]
        if part.startswith("u"):
            return chr(int(part[1:], 16))
        return {"t": "\t", "n": "\n", "r": "\r", "f": "\f"}.get(part, part)
    return re.sub(r"\\(u[0-9a-fA-F]{4}|.)", replace, value)


def escape(value):
    if has_control(value) or "," in value or not Path(value).is_absolute():
        raise SetupError(1, "JDK path cannot be represented safely in Gradle's comma-separated paths.")
    return "".join("\\" + char if char in "\\ :=#!" else char for char in value)


def merge(text, paths, remove=False):
    lines = text.splitlines(keepends=True)
    properties, markers = [], []
    continued = False
    pattern = re.compile(r"^([ \t]*" + re.escape(KEY) + r"[ \t]*(?:[=:][ \t]*|[ \t]+))(.*?)(\r?\n)?$")
    for index, line in enumerate(lines):
        match = pattern.fullmatch(line)
        marker = line.lstrip().startswith("# app-sandbox-setup:gradle-toolchains")
        if continued and (match or marker):
            raise SetupError(1, "Managed Gradle line is inside a continued property; use manual instructions.")
        if match:
            if len(match[2]) - len(match[2].rstrip("\\")) & 1:
                raise SetupError(1, "Continued Gradle paths property is unsupported; use manual instructions.")
            properties.append((index, match))
        if marker:
            markers.append(index)
        content = line.rstrip("\r\n")
        continued = (len(content) - len(content.rstrip("\\"))) % 2 == 1 if (
            continued or not content.lstrip().startswith(("#", "!"))) else False
    if len(properties) > 1 or len(markers) > 1:
        raise SetupError(1, "Duplicate Gradle paths/managed markers; refused for this file.")
    tracked = []
    if markers:
        try:
            line = lines[markers[0]].rstrip("\r\n")
            if not line.startswith(MARKER):
                raise ValueError()
            tracked = json.loads(line[len(MARKER):])
            if not isinstance(tracked, list) or any(not isinstance(p, str) for p in tracked):
                raise ValueError()
            for path in tracked:
                escape(path)
        except (ValueError, TypeError):
            raise SetupError(1, "Malformed Gradle managed marker; refused for this file.") from None
    tokens = properties[0][1][2].split(",") if properties else []
    existing = [unescape(value.strip()) for value in tokens if value.strip()]
    added = [path for path in paths if path not in existing] if not remove else []
    removed = [path for path in tracked if path in existing] if remove else []
    if not remove and not added:
        return text, [], []
    if added and not properties and continued:
        raise SetupError(1, "Last Gradle property is continued; cannot safely append the paths key.")
    if remove:
        tokens = [value for value in tokens if unescape(value.strip()) not in tracked]
        tracked = []
    else:
        tokens += [escape(path) for path in added]
        tracked = list(dict.fromkeys(tracked + added))
    if properties and (added or removed):
        index, match = properties[0]
        lines[index] = match[1] + ",".join(tokens) + (match[3] or "")
    elif added:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append(KEY + "=" + ",".join(tokens) + "\n")
    if markers:
        lines[markers[0]] = MARKER + json.dumps(tracked, separators=(",", ":")) + "\n" if tracked else ""
    elif tracked:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append(MARKER + json.dumps(tracked, separators=(",", ":")) + "\n")
    return "".join(lines), added, removed


def plan(args, home, connection):
    path = home / ".gradle/gradle.properties"
    state = profile_store.snapshot(path)
    paths, evidence = needed(connection, home, os.environ) if args.action != "remove" else ([], [])
    text, added, removed = merge(state["text"], paths, args.action == "remove")
    public = {"operation": "gradle-toolchains " + ("remove" if args.action == "remove" else "apply"),
              "target": str(path), "added": added, "removed": removed, "warnings": [NOTE],
              "changed": text != state["text"], "repair_needed": bool(paths)}
    public["digest"] = hashlib.sha256(canonical({
        "public": public, "file": profile_store.fingerprint(state), "evidence": evidence,
    }).encode()).hexdigest()
    return public, path, state, text, {"projects": [], "warnings": [], "skipped": []}
