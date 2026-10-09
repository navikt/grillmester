"""Profile opt-in observations shared by optional activation and normal plans."""

import os
from pathlib import Path

from . import profile, profile_store, toolchain_discovery
from .paths import SetupError


def mise_paths(home, env=None):
    env = os.environ if env is None else env
    data = env.get("MISE_DATA_DIR") or (
        str(Path(env["XDG_DATA_HOME"]) / "mise") if env.get("XDG_DATA_HOME")
        else str(home / ".local/share/mise"))
    shims = str(Path(profile.safe_path(data)) / "shims")
    resolved = Path(shims).resolve()
    if resolved == home or resolved in home.parents:
        raise SetupError(1, "Shim directory resolves to a broad HOME/ancestor grant; refused.")
    readonly = [shims, str(resolved)]
    binary = toolchain_discovery.managers(home, env).get("mise")
    if binary:
        path = Path(profile.safe_path(str(binary)))
        for directory in (path.parent, path.resolve().parent):
            if directory == home:
                raise SetupError(1, "mise binary directory is HOME itself; move mise to a dedicated directory.")
            if directory != home and home in directory.parents:
                readonly.append(str(directory))
    return shims, list(dict.fromkeys(readonly)), binary


def read_profile(home, path):
    state = profile_store.snapshot(path)
    try:
        current = profile.config(state["text"])
        if current:
            readonly = current["readonly"] + [str(Path(p).resolve()) for p in current["readonly"]]
            if any(Path(p) == home or Path(p) in home.parents for p in readonly):
                raise ValueError()
            current = {**current, "readonly": list(dict.fromkeys(readonly))}
    except ValueError:
        raise SetupError(1, "Malformed/unrecognized profile markers; refused for this file.") from None
    return state, current


def observe(home, shell=None, env=None):
    env = os.environ if env is None else env
    kind, path = profile.target(home, shell or env.get("SHELL", ""), env,
                                lambda p: p.exists() or p.is_symlink())
    state, current = (read_profile(home, path) if path else
                      ({"exists": False, "mode": 0o600, "text": ""}, None))
    return kind, path, state, current


def readonly_facts(home, warnings=None, env=None):
    env = os.environ if env is None else env
    readonly = []
    unknown = False
    try:
        _, candidates, _ = mise_paths(home, env)
        for path in profile.candidates(home, env):
            try:
                _, current = read_profile(home, path)
                if current:
                    readonly.extend(current["readonly"])
            except (SetupError, OSError, ValueError, RuntimeError):
                unknown = True
    except (SetupError, OSError, ValueError, RuntimeError):
        candidates, unknown = [], True
    if unknown:
        if warnings is not None:
            warnings.append("Profile opt-in state unavailable; existing readonly hardening retained. "
                            "Use the separate profile plan to inspect; no profile writes in default setup.")
        # Unknown is not inactive: never retire hardening on an unreadable file.
        candidates = []
    return list(dict.fromkeys(readonly)), candidates
