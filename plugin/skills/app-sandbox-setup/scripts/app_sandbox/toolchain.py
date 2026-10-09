"""Pure pin detection and per-tool sandbox decisions; no host observations."""

import json
import re
import shlex
from typing import Any


def major(version: str) -> str:
    match = re.match(r"(?:[A-Za-z]+[-@])?v?(\d+)(?:\.(\d+))?", version.strip())
    if not match:
        return ""
    return match[2] if match[1] == "1" and match[2] else match[1]


def detect(files: dict[str, str]) -> dict[str, dict[str, str]]:
    pins = {}

    def add(tool, version, source, manager=""):
        if tool != "java" and not re.fullmatch(r"v?\d+(?:\.\d+){0,2}", version):
            return
        if major(version):
            # Java decisions use only a numeric major, never arbitrary pin text.
            pins.setdefault(tool, {"version": major(version) if tool == "java" else version.lstrip("v"),
                                  "major": major(version),
                                  "source": source, "manager": manager})
    for name in (".mise.toml", "mise.toml"):
        tools = False
        for line in files.get(name, "").splitlines():
            if line.strip().startswith("["):
                tools = line.strip() == "[tools]"
            if tools:
                match = re.match(r'\s*(java|node|pnpm)\s*=\s*["\']([^"\']+)["\']', line)
                if match and major(match[2]):
                    add(match[1], match[2], name, "mise")
    for line in files.get(".tool-versions", "").splitlines():
        match = re.match(r"\s*(java|nodejs|node|pnpm)\s+(\S+)", line)
        if match:
            add("node" if match[1] == "nodejs" else match[1], match[2], ".tool-versions", "asdf")
    for name, tool in ((".java-version", "java"), (".nvmrc", "node"), (".node-version", "node")):
        add(tool, files.get(name, "").strip(), name)
    match = re.search(r"^\s*java\s*=\s*([^\s#]+)", files.get(".sdkmanrc", ""), re.MULTILINE)
    if match:
        add("java", match[1].strip("'\""), ".sdkmanrc", "sdkman")
    try:
        package = json.loads(files.get("package.json", "{}"))
        value = package.get("packageManager", "") if isinstance(package, dict) else ""
        match = re.fullmatch(r"pnpm@(\d+(?:\.\d+){0,2})(?:\+[^ \r\n]+)?", value) if isinstance(value, str) else None
        if match:
            # packageManager is the more precise pnpm version contract.
            prior = pins.pop("pnpm", {})
            add("pnpm", match[1], "package.json", prior.get("manager", "packageManager"))
    except (ValueError, RecursionError):
        pass
    for name in ("build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"):
        match = re.search(r"\b(?:jvmToolchain|JavaLanguageVersion\.of)\s*\(\s*(\d+)\s*\)",
                          files.get(name, ""))
        if match:
            add("java", match[1], name)
    return pins


def decide(observation: dict[str, Any]) -> list[dict[str, Any]]:
    decisions = []
    pin = observation.get("pins", {}).get("java")
    if pin:
        command = "mise" if observation.get("managers", {}).get("mise") and pin["manager"] in ("mise", "asdf") else None
        home = next((item["home"] for item in observation.get("jdks", [])
                     if item["major"] == pin["major"]), None)
        if not command and home:
            command = "JAVA_HOME"
        decisions.append({"tool": "java", "pin": pin, "command": command,
                          "home": home if command == "JAVA_HOME" else None,
                          "warning": None if command else
                          f'no matching JDK found for Java {pin["major"]}; install it outside the sandbox'})
    for tool in ("node", "pnpm"):
        pin = observation.get("pins", {}).get(tool)
        if not pin:
            continue
        command = None
        known = observation.get("session_path") is not None
        if (known and not observation.get("resolved", {}).get(tool)
                and pin["manager"] in ("mise", "asdf")):
            command = "mise"
        decisions.append({"tool": tool, "pin": pin, "command": command,
                          "warning": observation.get("session_warning") if not known else None})
    return decisions


def command_prefix(decision: dict[str, Any]) -> str:
    if decision["command"] == "mise":
        return "mise exec -- "
    if decision["command"] == "JAVA_HOME":
        return "JAVA_HOME=" + shlex.quote(decision["home"]) + " "
    return ""


def classify(tool: str, code: int, output: str, pin: dict[str, str]):
    """Return only a category and numeric version; never return command output."""
    lower = output.lower()
    if "operation not permitted" in lower or "eperm" in lower:
        return "seatbelt", ""
    if "not installed" in lower or "missing jdk" in lower or "no matching jdk" in lower:
        return "not-installed", ""
    if "unable to locate a java runtime" in lower or "not found" in lower:
        return "environment", ""
    if "java" in tool:
        match = re.search(r'\b(?:openjdk|java)\s+version\s+"(\d+(?:\.\d+)*)', output)
    elif tool == "gradlew":
        match = re.search(r"(?:Launcher JVM|JVM):\s*(\d+(?:\.\d+)*)", output)
    else:
        match = re.search(r"(?m)^v?(\d+(?:\.\d+){0,2})(?:\s|$)", output.strip())
    version = match[1] if match else ""
    expected = pin.get("major")
    matches = not expected or major(version) == expected
    if tool == "pnpm" and pin.get("version"):
        matches = version.split(".")[:len(pin["version"].split("."))] == pin["version"].split(".")
    return ("ok" if not code and version and matches else "environment"), version
