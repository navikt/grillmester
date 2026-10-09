"""Bounded project commands in the current sandbox session, not a login shell."""

import errno
import os
import subprocess

from . import toolchain, toolchain_discovery


def execute(name, command, env, repo, pin, timeout, runner):
    result = {"name": name, "expected": pin.get("version", "available") if name == "pnpm" else pin.get("major", "available"),
              "actual": "unknown", "category": "environment", "gate": True}
    try:
        completed = runner(command, env=env, cwd=str(repo), stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=timeout)
        category, version = toolchain.classify(name, completed.returncode,
                                               completed.stdout + "\n" + completed.stderr, pin)
        result.update(category=category, actual=version or "unknown")
    except OSError as error:
        result["category"] = "seatbelt" if error.errno == errno.EPERM else "environment"
    except subprocess.TimeoutExpired:
        result["actual"] = "timeout"
    return result


def run(repo, home, runner=None):
    runner = subprocess.run if runner is None else runner
    observation = toolchain_discovery.observe(repo, home, capture_session=False)
    pins = observation["pins"]
    decisions = {decision["tool"]: decision for decision in toolchain.decide(observation)}
    env = dict(os.environ, MISE_EXEC_AUTO_INSTALL="false", COREPACK_ENABLE_DOWNLOAD_PROMPT="0",
               COREPACK_ENABLE_NETWORK="0", npm_config_manage_package_manager_versions="false")
    results = []
    if observation["gradlew"]:
        pin = pins.get("java", {})
        java = decisions.get("java")
        bare = execute("java", ["java", "-version"], env, repo, pin, 20, runner)
        if java and java["command"]:
            form = "mise exec -- java" if java["command"] == "mise" else "JAVA_HOME=… java"
            bare.update(gate=False, info="bare java; agents use " + form)
        results.append(bare)
        prefix = []
        corrected_env = dict(env)
        if java and java["command"] == "mise":
            prefix = ["mise", "exec", "--"]
        elif java and java["command"] == "JAVA_HOME":
            corrected_env["JAVA_HOME"] = java["home"]
        if java and java["command"]:
            results.append(execute("managed java", prefix + ["java", "-version"], corrected_env,
                                   repo, pin, 20, runner))
        elif java and java["warning"]:
            results.append({"name": "managed java", "category": "not-installed",
                            "expected": pin["major"], "actual": "missing JDK", "gate": True})
        results.append(execute("gradlew", prefix + ["./gradlew", "--version",
                               "-Dorg.gradle.java.installations.auto-download=false"],
                               corrected_env, repo, pin, 120, runner))
    if observation["package_json"] or observation["node_required"] or observation["pnpm_required"]:
        for tool in ("node", "pnpm"):
            required = observation[tool + "_required"]
            if tool == "pnpm" and not required:
                continue
            pin = pins.get(tool, {})
            decision = decisions.get(tool)
            bare = execute(tool, [tool, "-v"], env, repo, pin, 20, runner)
            managed = decision is not None and decision["command"] == "mise"
            if managed:
                bare.update(gate=False, info=f"bare {tool}; agents use mise exec -- {tool}")
            elif not required:
                bare.update(gate=False, info="node has no version pin or engines.node requirement")
            results.append(bare)
            if managed:
                result = execute(tool, ["mise", "exec", "--", tool, "-v"], env, repo, pin, 20, runner)
                result["name"] = "managed " + tool
                results.append(result)
    return results
