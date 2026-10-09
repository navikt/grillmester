"""Ordered sandbox rules.

Add a new path rule as one row in RULES here. Derived views preserve the legacy
order: changing that order changes diagnostics and confirmation digests.

Behavioural values: condition="when_exists" selects rw/ro discovery paths;
condition="always" selects readonly hardening paths. Deny conditions
"when_file"/"qualified_dir" describe qualification, which uses kind="file"
and the backup exception; kind="any"/"dir" are otherwise descriptive.
group="docker" selects Docker discovery order, and group="backup" identifies
the unconditional backup deny. Other groups ("tool", "app", "secret",
"hardening") are descriptive, not control flow.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Rule:
    path: str
    access: str
    kind: str
    condition: str
    group: str
    reason: str
    status: str = "active"
    docker_order: int = 0


RULES = (
    Rule("<profile-readonly>", "ro", "dir", "profile_opt_in", "hardening",
         "protect shim persistence before shell activation"),
    Rule(".gradle", "rw", "any", "when_exists", "tool", "build cache"),
    Rule(".m2", "rw", "any", "when_exists", "tool", "build cache"),
    Rule(".npm", "rw", "any", "when_exists", "tool", "package cache"),
    Rule(".cache", "rw", "any", "when_exists", "tool", "tool cache"),
    Rule(".config", "rw", "any", "when_exists", "tool", "tool configuration"),
    Rule(".local/share", "rw", "any", "when_exists", "tool", "tool data"),
    Rule(".local/state", "rw", "any", "when_exists", "tool", "tool state"),
    Rule("Library/Caches", "rw", "any", "when_exists", "tool", "tool cache"),
    Rule("Library/pnpm", "rw", "any", "when_exists", "tool", "package cache"),
    Rule(".bun", "rw", "any", "when_exists", "tool", "tool install"),
    Rule(".nvm", "rw", "any", "when_exists", "tool", "tool install"),
    Rule(".rd", "rw", "any", "when_exists", "docker", "Docker runtime", docker_order=2),
    Rule(".docker", "rw", "any", "when_exists", "docker", "Docker configuration", docker_order=1),
    Rule("/tmp", "rw", "any", "when_exists", "tool", "temporary files"),
    Rule("/private/tmp", "rw", "any", "when_exists", "tool", "temporary files"),
    Rule("Library/Application Support/kotlin", "rw", "any", "when_exists", "tool", "Kotlin data"),
    Rule(".konan", "rw", "any", "when_exists", "tool", "Kotlin native cache"),
    Rule(".testcontainers.properties", "rw", "any", "when_exists", "docker", "Testcontainers configuration", docker_order=6),
    Rule(".colima", "rw", "any", "when_exists", "docker", "Docker runtime", docker_order=3),
    Rule(".orbstack", "rw", "any", "when_exists", "docker", "Docker runtime", docker_order=4),
    Rule(".lima", "rw", "any", "when_exists", "docker", "Docker runtime", docker_order=5),
    Rule("go", "rw", "any", "when_exists", "tool", "Go workspace"),
    Rule(".cargo", "rw", "any", "when_exists", "tool", "Rust tool install"),
    Rule(".yarn", "rw", "any", "when_exists", "tool", "package cache"),
    Rule(".copilot/installed-plugins", "ro", "any", "when_exists", "app", "installed plugins"),
    Rule(".copilot/agents", "ro", "any", "when_exists", "app", "agents"),
    Rule(".copilot/extensions", "ro", "any", "when_exists", "app", "extensions"),
    Rule(".copilot/marketplace-cache", "ro", "any", "when_exists", "app", "marketplace cache"),
    Rule(".agents", "ro", "any", "when_exists", "tool", "agents"),
    Rule(".claude/skills", "ro", "any", "when_exists", "tool", "skills"),
    Rule(".gitconfig", "ro", "any", "when_exists", "tool", "Git configuration"),
    Rule("Library/Java/JavaVirtualMachines", "ro", "any", "when_exists", "tool", "JDK installations"),
    Rule("/Library/Java/JavaVirtualMachines", "ro", "any", "when_exists", "tool", "JDK installations"),
    Rule(".sdkman", "ro", "any", "when_exists", "tool", "tool install"),
    Rule(".asdf", "ro", "any", "when_exists", "tool", "tool install"),
    Rule(".jenv", "ro", "any", "when_exists", "tool", "tool install"),
    Rule(".volta", "ro", "any", "when_exists", "tool", "tool install"),
    Rule(".pyenv", "ro", "any", "when_exists", "tool", "tool install"),
    Rule(".rustup", "ro", "any", "when_exists", "tool", "tool install"),
    Rule(".local/bin", "ro", "any", "when_exists", "tool", "tool executables"),
    Rule("Library/Application Support/fnm", "ro", "any", "when_exists", "tool", "tool install"),
    Rule(".npmrc", "ro", "any", "when_exists", "tool", "package configuration"),
    Rule(".yarnrc.yml", "ro", "any", "when_exists", "tool", "package configuration"),
    Rule(".config/gh/hosts.yml", "ro", "any", "when_exists", "secret", "GitHub configuration"),
    Rule(".config/git", "ro", "any", "always", "hardening", "protect executable configuration"),
    Rule(".config/fish", "ro", "any", "always", "hardening", "protect executable configuration"),
    Rule(".config/mise", "ro", "any", "always", "hardening", "protect executable configuration"),
    Rule(".config/direnv", "ro", "any", "always", "hardening", "protect executable configuration"),
    Rule(".config/gh/config.yml", "ro", "any", "always", "hardening", "protect executable configuration"),
    Rule(".gradle/init.d", "ro", "any", "always", "hardening", "protect executable configuration"),
    Rule(".gradle/init.gradle", "ro", "any", "always", "hardening", "protect executable configuration"),
    Rule(".gradle/init.gradle.kts", "ro", "any", "always", "hardening", "protect executable configuration"),
    Rule(".gradle/gradle.properties", "ro", "any", "always", "hardening", "protect build configuration"),
    Rule(".docker/cli-plugins", "ro", "any", "always", "hardening", "protect Docker plugins"),
    Rule(".docker/config.json", "ro", "any", "always", "hardening", "protect Docker configuration"),
    Rule("Library/Caches/copilot", "ro", "any", "always", "hardening", "protect app cache"),
    Rule(".ssh", "deny", "dir", "qualified_dir", "secret", "SSH credentials"),
    Rule(".aws", "deny", "dir", "qualified_dir", "secret", "AWS credentials"),
    Rule(".gnupg", "deny", "dir", "qualified_dir", "secret", "signing credentials"),
    Rule(".kube", "deny", "dir", "qualified_dir", "secret", "cluster credentials"),
    Rule(".config/gcloud", "deny", "dir", "qualified_dir", "secret", "cloud credentials"),
    Rule("Library/Keychains", "deny", "dir", "qualified_dir", "secret", "keychain"),
    Rule(".netrc", "deny", "file", "when_file", "secret", "network credentials"),
    Rule(".copilot/data.db", "deny", "file", "when_file", "app", "app database"),
    Rule(".copilot/app-sandbox-setup-backups", "deny", "dir", "always", "backup", "sandbox backups"),
    Rule(".copilot/settings.json", "deny", "file", "when_file", "app", "app settings"),
    Rule(".copilot/config.json", "deny", "file", "when_file", "app", "app configuration"),
    Rule(".copilot/mcp-oauth-config", "deny", "dir", "qualified_dir", "secret", "MCP OAuth credentials"),
    Rule(".config/github-copilot", "deny", "dir", "qualified_dir", "secret", "Copilot credentials"),
    Rule(".config/configstore", "deny", "dir", "qualified_dir", "secret", "tool credentials"),
    Rule(".config/op", "deny", "dir", "qualified_dir", "secret", "password manager"),
    Rule(".azure", "deny", "dir", "qualified_dir", "secret", "Azure credentials"),
    Rule(".copilot/session-state", "rw", "any", "always", "app",
         "the app grants its own session files", "retired"),
    Rule("Library/Application Support/Google/Chrome for Testing", "rw", "any", "always", "tool",
         "Chromium needs denied macOS IPC; no path grant helps", "retired"),
    Rule(".copilot/data.db-wal", "deny", "any", "always", "app",
         "~/.copilot is not readable in the sandbox; a deny placeholder could break the app's SQLite WAL", "retired"),
    Rule(".copilot/data.db-shm", "deny", "any", "always", "app",
         "~/.copilot is not readable in the sandbox; a deny placeholder could break the app's SQLite WAL", "retired"),
)

ACCESS_FIELDS = {"rw": "readwritePaths", "ro": "readonlyPaths", "deny": "deniedPaths"}


def paths(access: str, condition: str) -> tuple[str, ...]:
    return tuple(rule.path for rule in RULES
                 if rule.status == "active" and rule.access == access and rule.condition == condition)


RW_PATHS = paths("rw", "when_exists")
RO_PATHS = paths("ro", "when_exists")
HARDENING_READONLY = paths("ro", "always")
# Preserve the historical Docker discovery order, independently of grant order.
DOCKER_PATHS = tuple(rule.path for rule in sorted(RULES, key=lambda row: row.docker_order)
                     if rule.status == "active" and rule.group == "docker")
DENIED_PATHS = tuple(rule.path for rule in RULES if rule.status == "active" and rule.access == "deny")
FILE_DENIED_PATHS = frozenset(rule.path for rule in RULES
                             if rule.status == "active" and rule.access == "deny" and rule.kind == "file")
RETIRED_GRANTS = {
    field: {rule.path: rule.reason for rule in RULES
            if rule.status == "retired" and ACCESS_FIELDS[rule.access] == field}
    for field in ("readwritePaths", "deniedPaths")
}
APP_CACHE_WRITABLE: set[str] = set()
BACKUP_DIRECTORY = next(rule.path for rule in RULES if rule.group == "backup")
APP_OWNED_DB_SUFFIXES = (".open-lock", "-wal", "-shm", "-journal")
PATH_FIELDS = ("readwritePaths", "readonlyPaths", "deniedPaths")
BOOL_FIELDS = ("allowOutbound", "allowLocalNetwork", "allowGitCredentials", "allowGhCredentials")
CREDENTIAL_WARNING = (
    "When credential masking is OFF: sandboxed processes see the real GH_TOKEN / git credentials. "
    "With outbound allowed, any build script or dependency could exfiltrate them. "
    "Use --mask-credentials to mask them instead; the proxy forces loopback deny, "
    "breaking Gradle daemon, Testcontainers, dev servers and Playwright even with allowLocalNetwork=true."
)
MASKING_SCOPE_WARNING = (
    "Credential masking covers only app-injected GH_TOKEN / git credential helper, NOT files "
    "on disk such as ~/.npmrc, gradle.properties or hosts.yml. Existing credential choices are preserved."
)
SYSTEM_AREAS = (
    "/System", "/Library", "/usr", "/bin", "/sbin", "/etc", "/var",
    "/private", "/opt", "/Applications",
)


def snapshot() -> dict[str, Any]:
    """Pass only data, never a module or filesystem callbacks, to the engine."""
    return {
        "RW_PATHS": RW_PATHS, "RO_PATHS": RO_PATHS, "HARDENING_READONLY": HARDENING_READONLY,
        "DOCKER_PATHS": DOCKER_PATHS, "DENIED_PATHS": DENIED_PATHS,
        "FILE_DENIED_PATHS": FILE_DENIED_PATHS, "BACKUP_DIRECTORY": BACKUP_DIRECTORY,
        "RETIRED_GRANTS": {field: dict(paths) for field, paths in RETIRED_GRANTS.items()},
        "SYSTEM_AREAS": SYSTEM_AREAS,
        "PROFILE_OPT_IN": any(rule.condition == "profile_opt_in" for rule in RULES),
    }
