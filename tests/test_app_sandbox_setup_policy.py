"""Rule-order contract and filesystem-free policy examples."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest import mock


SCRIPT = (Path(__file__).resolve().parents[1]
          / "plugin/skills/app-sandbox-setup/scripts/app_sandbox_setup.py")
with mock.patch.object(sys, "dont_write_bytecode", True):
    spec = importlib.util.spec_from_file_location("app_sandbox_setup_policy_entry", SCRIPT)
    assert spec and spec.loader
    spec.loader.exec_module(importlib.util.module_from_spec(spec))
    from app_sandbox import policy, rules
    from app_sandbox.facts import Facts, Options, PathFact


# Legacy constants copied verbatim from e69e97b; never derive expectations from
# RULES or import the differential oracle.
RW_PATHS = (
    ".gradle", ".m2", ".npm", ".cache", ".config", ".local/share", ".local/state",
    "Library/Caches", "Library/pnpm", ".bun", ".nvm", ".rd", ".docker",
    "/tmp", "/private/tmp",
    "Library/Application Support/kotlin", ".konan", ".testcontainers.properties",
    ".colima", ".orbstack", ".lima", "go", ".cargo", ".yarn",
)
RO_PATHS = (
    ".copilot/installed-plugins", ".copilot/agents", ".copilot/extensions",
    ".copilot/marketplace-cache", ".agents", ".claude/skills", ".gitconfig",
    "Library/Java/JavaVirtualMachines", "/Library/Java/JavaVirtualMachines",
    ".sdkman", ".asdf", ".jenv", ".volta", ".pyenv", ".rustup", ".local/bin",
    "Library/Application Support/fnm", ".npmrc", ".yarnrc.yml",
    ".config/gh/hosts.yml",
)
HARDENING_READONLY = (
    ".config/git", ".config/fish", ".config/mise", ".config/direnv",
    ".config/gh/config.yml", ".gradle/init.d", ".gradle/init.gradle",
    ".gradle/init.gradle.kts", ".gradle/gradle.properties",
    ".docker/cli-plugins", ".docker/config.json", "Library/Caches/copilot",
)
DOCKER_PATHS = (".docker", ".rd", ".colima", ".orbstack", ".lima", ".testcontainers.properties")
APP_CACHE_WRITABLE: set[str] = set()
RETIRED_GRANTS = {
    "readwritePaths": {
        ".copilot/session-state": "the app grants its own session files",
        "Library/Application Support/Google/Chrome for Testing":
            "Chromium needs denied macOS IPC; no path grant helps",
    },
    "deniedPaths": {
        ".copilot/data.db-wal":
            "~/.copilot is not readable in the sandbox; a deny placeholder could break the app's SQLite WAL",
        ".copilot/data.db-shm":
            "~/.copilot is not readable in the sandbox; a deny placeholder could break the app's SQLite WAL",
    },
}
DENIED_PATHS = (
    ".ssh", ".aws", ".gnupg", ".kube", ".config/gcloud", "Library/Keychains",
    ".netrc", ".copilot/data.db",
    ".copilot/app-sandbox-setup-backups", ".copilot/settings.json",
    ".copilot/config.json", ".copilot/mcp-oauth-config",
    ".config/github-copilot", ".config/configstore", ".config/op", ".azure",
)
FILE_DENIED_PATHS = frozenset((
    ".netrc", ".copilot/data.db", ".copilot/settings.json", ".copilot/config.json",
))
BACKUP_DIRECTORY = ".copilot/app-sandbox-setup-backups"
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


class RulesTest(unittest.TestCase):
    def test_derived_views_equal_legacy_constants_in_order(self):
        for name in (
            "RW_PATHS", "RO_PATHS", "HARDENING_READONLY", "DOCKER_PATHS",
            "APP_CACHE_WRITABLE", "RETIRED_GRANTS", "DENIED_PATHS",
            "FILE_DENIED_PATHS", "BACKUP_DIRECTORY", "APP_OWNED_DB_SUFFIXES",
            "PATH_FIELDS", "BOOL_FIELDS", "CREDENTIAL_WARNING",
            "MASKING_SCOPE_WARNING", "SYSTEM_AREAS",
        ):
            with self.subTest(name=name):
                self.assertEqual(globals()[name], getattr(rules, name))
                if name == "RETIRED_GRANTS":
                    for field in RETIRED_GRANTS:
                        self.assertEqual(list(RETIRED_GRANTS[field].items()),
                                         list(rules.RETIRED_GRANTS[field].items()))
        self.assertEqual(len(rules.RULES), len({row.path for row in rules.RULES}))


class PurePolicyTest(unittest.TestCase):
    home = "/fixture-home"
    project = {"id": "p1", "name": "example", "main_repo_path": "/fixture-home/code/repo",
               "sandbox_enabled": 0}

    def facts(self, **values):
        return Facts(self.home, projects=(dict(self.project),), **values)

    def plan(self, facts, before=None, options=Options()):
        existing = {"p1": json.dumps(before)} if before is not None else {}
        original_facts, original_existing = copy.deepcopy(facts), copy.deepcopy(existing)
        with mock.patch("builtins.open", side_effect=AssertionError("policy must not do IO")), \
                mock.patch.object(Path, "resolve", side_effect=AssertionError("no resolve")), \
                mock.patch.object(Path, "stat", side_effect=AssertionError("no stat")), \
                mock.patch.object(Path, "exists", side_effect=AssertionError("no exists")):
            result = policy.compute_plan(rules.snapshot(), facts, existing, options)
        self.assertEqual(original_facts, facts)
        self.assertEqual(original_existing, existing)
        return result

    def test_credential_choice_table_and_unknown_fields(self):
        for flag, before, expected in (
            (None, {}, False), (None, {"allowGitCredentials": True}, True),
            (True, {"allowGitCredentials": False}, True),
            (False, {"allowGitCredentials": True}, False),
        ):
            with self.subTest(flag=flag, before=before):
                before = dict(before, unknown={"nested": [7, True]})
                plan = self.plan(self.facts(), before, Options(mask=flag))
                after = plan["projects"][0]["after"]["policy"]
                self.assertEqual(expected, after["allowGitCredentials"])
                self.assertEqual(before["unknown"], after["unknown"])
                self.assertTrue(after["allowOutbound"])
                self.assertTrue(after["allowLocalNetwork"])

    def test_deny_qualification_and_placeholder_table(self):
        for relative, state, writable, qualifies, removes in (
            (".netrc", PathFact("", exists=True, file=True), False, True, False),
            (".netrc", PathFact("", exists=True, directory=True, empty=True), False, False, True),
            (".aws", PathFact("", exists=True, directory=True, empty=True), False, False, True),
            (".aws", PathFact("", exists=True, directory=True, empty=True), True, True, False),
            (".config/op", PathFact(""), True, True, False),
            (".aws", PathFact("", symlink=True), True, False, False),
            (".azure", PathFact("", exists=True, file=True), True, False, False),
        ):
            with self.subTest(relative=relative, writable=writable, state=state):
                path = self.home + "/" + relative
                facts = self.facts(paths={path: state}, roots=(self.home,) if writable else ())
                plan = self.plan(facts)
                after = plan["projects"][0]["after"]["policy"]
                self.assertEqual(qualifies, path in after["deniedPaths"])
                self.assertEqual(removes, path in [entry["path"] for entry in plan["placeholder_removals"]])

    def test_merge_conflicts_retirement_and_order(self):
        facts = self.facts(
            paths={self.home + "/.config": PathFact(self.home + "/.config", exists=True)},
            roots=(self.home + "/code",),
        )
        before = {
            "readwritePaths": [self.home + "/user", self.home + "/user",
                              self.home + "/.config/git", self.home + "/.copilot/session-state",
                              "relative", "/bad\nentry"],
            "deniedPaths": [self.home + "/code", self.home + "/.config"],
        }
        plan = self.plan(facts, before)
        after = plan["projects"][0]["after"]["policy"]
        self.assertEqual([self.home + "/user"], after["readwritePaths"])
        self.assertEqual([self.home + "/code", self.home + "/.config",
                          self.home + "/.config/gcloud",
                          self.home + "/" + BACKUP_DIRECTORY,
                          self.home + "/.config/github-copilot",
                          self.home + "/.config/configstore",
                          self.home + "/.config/op"], after["deniedPaths"])
        self.assertTrue(any("retired" in warning for warning in plan["warnings"]))

    def test_no_docker_removes_exact_grants_not_user_descendants(self):
        docker = self.home + "/.docker"
        child = docker + "/user-cache"
        facts = self.facts(
            paths={docker: PathFact(docker, exists=True)}, docker=(docker,),
        )
        plan = self.plan(facts, {"readwritePaths": [docker, child]}, Options(no_docker=True))
        self.assertEqual([child], plan["projects"][0]["after"]["policy"]["readwritePaths"])
        self.assertFalse(any(path.startswith(docker) for path in
                             plan["projects"][0]["after"]["policy"]["readonlyPaths"]))

    def test_symlink_and_inode_relations_use_only_supplied_identity(self):
        target = self.home + "/.config/git"
        for identity in ("resolved", "inode"):
            with self.subTest(identity=identity):
                if identity == "resolved":
                    states = {"/alias": PathFact(target)}
                else:
                    states = {"/alias": PathFact("/alias", inode=(1, 2)),
                              target: PathFact(target, inode=(1, 2))}
                plan = self.plan(self.facts(paths=states), {"readwritePaths": ["/alias"]})
                self.assertNotIn("/alias", plan["projects"][0]["after"]["policy"]["readwritePaths"])

    def test_corrupt_project_skipped_and_digest_excludes_names_and_warnings(self):
        facts = self.facts()
        first = self.plan(facts)
        renamed = dict(self.project, name="renamed")
        second = self.plan(Facts(self.home, projects=(renamed,), git_warnings=("diagnostic",)))
        self.assertEqual(first["digest"], second["digest"])
        corrupt = policy.compute_plan(rules.snapshot(), facts, {"p1": '{"deniedPaths": [false]}'}, Options())
        self.assertEqual(["p1"], corrupt["skipped"])
        self.assertEqual([], corrupt["projects"])
        self.assertTrue(any("corrupt policy skipped" in warning for warning in corrupt["warnings"]))


if __name__ == "__main__":
    unittest.main()
