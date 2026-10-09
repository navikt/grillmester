"""Rule-order contract and filesystem-free policy examples."""

from __future__ import annotations

import copy
import errno
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


SCRIPT = (Path(__file__).resolve().parents[1]
          / "plugin/skills/app-sandbox-setup/scripts/app_sandbox_setup.py")
with mock.patch.object(sys, "dont_write_bytecode", True):
    spec = importlib.util.spec_from_file_location("app_sandbox_setup_policy_entry", SCRIPT)
    assert spec and spec.loader
    spec.loader.exec_module(importlib.util.module_from_spec(spec))
    from app_sandbox import discovery, policy, rules
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
    def test_docker_order_is_unique(self):
        orders = [row.docker_order for row in rules.RULES
                  if row.status == "active" and row.group == "docker"]
        self.assertEqual(len(orders), len(set(orders)))

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


class DiscoveryFactsTest(unittest.TestCase):
    def test_stat_errors_fall_back_to_resolved_identity(self):
        path = Path("/synthetic/Policy-Path")
        for code in (errno.EACCES, errno.EPERM, errno.ENAMETOOLONG):
            with self.subTest(code=code), \
                    mock.patch.object(Path, "exists", return_value=True), \
                    mock.patch.object(Path, "resolve", return_value=path), \
                    mock.patch.object(Path, "stat", side_effect=OSError(code, "synthetic")):
                state = discovery.path_fact(path)
                self.assertEqual(str(path).casefold(), state.resolved)
                self.assertIsNone(state.inode)
                self.assertTrue(state.exists)
                self.assertFalse(state.file)
                self.assertFalse(state.directory)
                self.assertFalse(state.symlink)
                facts = Facts("/synthetic", paths={str(path): state})
                self.assertTrue(facts.same(path, Path(str(path).lower())))
                self.assertTrue(facts.under(path / "child", Path(str(path).lower())))
                self.assertTrue(facts.under(path, Path("/synthetic")))

    def test_exists_errors_leave_observations_false(self):
        path = Path("/synthetic/Policy-Path")
        for code in (errno.EACCES, errno.EPERM, errno.ENAMETOOLONG):
            with self.subTest(code=code), \
                    mock.patch.object(Path, "exists", side_effect=OSError(code, "synthetic")), \
                    mock.patch.object(Path, "stat", return_value=mock.Mock(st_dev=1, st_ino=2)), \
                    mock.patch.object(Path, "is_file", return_value=True), \
                    mock.patch.object(Path, "is_dir", return_value=True), \
                    mock.patch.object(Path, "is_symlink", return_value=True), \
                    mock.patch.object(Path, "resolve", return_value=path):
                state = discovery.path_fact(path)
                self.assertEqual(str(path).casefold(), state.resolved)
                self.assertIsNone(state.inode)
                self.assertFalse(state.exists)
                self.assertFalse(state.file)
                self.assertFalse(state.directory)
                self.assertFalse(state.symlink)
                self.assertFalse(state.empty)
                self.assertFalse(state.resolution_failed)

    def test_metadata_errors_preserve_other_observations(self):
        path = Path("/synthetic/Policy-Path")
        for method, field in (
            ("stat", "inode"), ("is_file", "file"),
            ("is_dir", "directory"), ("is_symlink", "symlink"),
        ):
            for code in (errno.EACCES, errno.EPERM, errno.ENAMETOOLONG):
                with self.subTest(method=method, code=code), \
                        mock.patch.object(Path, "exists", return_value=True), \
                        mock.patch.object(Path, "stat", return_value=mock.Mock(st_dev=1, st_ino=2)), \
                        mock.patch.object(Path, "is_file", return_value=True), \
                        mock.patch.object(Path, "is_dir", return_value=True), \
                        mock.patch.object(Path, "is_symlink", return_value=True), \
                        mock.patch.object(Path, "resolve", return_value=path), \
                        mock.patch.object(Path, method, side_effect=OSError(code, "synthetic")):
                    state = discovery.path_fact(path)
                    self.assertTrue(state.exists)
                    self.assertEqual(None if field == "inode" else (1, 2), state.inode)
                    self.assertEqual(field != "file", state.file)
                    self.assertEqual(field != "directory", state.directory)
                    self.assertEqual(field != "symlink", state.symlink)

    def test_capture_preserves_only_oracle_unguarded_checks(self):
        home = Path("/synthetic-home")
        for relative, method in (
            (".gradle", "exists"), (".config/git", "exists"),
            (".netrc", "is_file"), (".aws", "is_dir"),
            (".docker", "exists"),
            (".copilot/app-sandbox-setup-backups", "is_dir"),
        ):
            for no_docker in (False, True):
                with self.subTest(relative=relative, no_docker=no_docker):
                    original = getattr(Path, method)

                    def denied(path):
                        if path == home / relative:
                            raise PermissionError(errno.EACCES, "synthetic")
                        return original(path)

                    with mock.patch.object(Path, method, denied):
                        if (relative == ".copilot/app-sandbox-setup-backups"
                                or relative == ".docker" and no_docker):
                            discovery.capture_paths(home, (), {}, (str(home / ".docker"),), no_docker)
                        else:
                            with self.assertRaises(PermissionError):
                                discovery.capture_paths(home, (), {}, (str(home / ".docker"),), no_docker)

    def test_rich_discovery_captures_every_engine_query(self):
        with tempfile.TemporaryDirectory(prefix="app-sandbox-policy-") as temporary:
            home = Path(temporary).resolve() / "home"
            for relative in (
                "code/repository", ".copilot", ".config/git", ".gradle",
                ".docker", ".fixture-docker", ".aws", ".ssh",
                "Library/Caches/copilot/writable", "Library/Caches/copilot/readonly",
                "Library/Caches/copilot-desktop-fixture", "user-denied",
            ):
                (home / relative).mkdir(parents=True, exist_ok=True)
            (home / ".ssh/marker").write_text("synthetic", encoding="utf-8")
            (home / ".netrc").write_text("synthetic", encoding="utf-8")
            (home / ".gitconfig").write_text(
                "[include]\n  path = included-git-config\n", encoding="utf-8",
            )
            (home / "included-git-config").write_text("[core]\n  autocrlf = false\n", encoding="utf-8")
            (home / "alias").symlink_to(home / ".config/git", target_is_directory=True)
            projects = [{"id": "p1", "name": "fixture", "main_repo_path": str(home / "code/repository"),
                         "sandbox_enabled": 0}]
            existing = {"p1": json.dumps({
                "readwritePaths": [str(home / "alias"), str(home / "user-missing/child")],
                "readonlyPaths": [str(home / "user-readonly")],
                "deniedPaths": [str(home / "user-denied")],
            })}
            with mock.patch.dict(os.environ, {
                "HOME": str(home), "DOCKER_HOST": "unix://" + str(home / ".fixture-docker/socket"),
                "ZDOTDIR": "", "MISE_DATA_DIR": "", "XDG_DATA_HOME": "", "JAVA_HOME": "",
                "ASDF_DATA_DIR": "", "SDKMAN_CANDIDATES_DIR": "", "GRADLE_USER_HOME": "",
            }), mock.patch.object(rules, "APP_CACHE_WRITABLE", {"writable"}), \
                    mock.patch.object(discovery.toolchain_discovery, "session_environment",
                                      return_value=({"PATH": "", "ZDOTDIR": ""}, None)), \
                    mock.patch.object(discovery.toolchain_discovery, "SYSTEM_JDK_ROOT", home / "system-jdks"):
                facts = discovery.gather(
                    home, projects, [(projects[0]["main_repo_path"], False)], existing,
                )
            original_path = Facts.path
            queries = set()

            def captured_path(snapshot, path):
                self.assertIn(str(path), snapshot.paths, "engine queried an uncaptured path")
                queries.add(str(path))
                return original_path(snapshot, path)

            with mock.patch.object(Facts, "path", captured_path):
                for no_docker in (False, True):
                    policy.compute_plan(rules.snapshot(), facts, existing, Options(no_docker=no_docker))
            self.assertIn(str(home / "alias"), queries)
            self.assertIn(str(home / "user-missing/child"), queries)


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
