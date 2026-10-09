"""Differential CLI contract: refactors must match the frozen e69e97b oracle.

No imports of either implementation: both run in isolated subprocesses against
the same absolute fixture paths, restored byte-for-byte between executions.
Only generated backup names are normalized; digests are compared verbatim.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / "plugin/skills/app-sandbox-setup/scripts/app_sandbox_setup.py"
REFERENCE = ROOT / "tests/fixtures/app_sandbox_setup_reference.py"
REFERENCE_HEADER = (
    b"# Frozen pre-refactor oracle from e69e97b.\n"
    b"# Used by tests/test_app_sandbox_setup_equivalence.py.\n"
    b"# Must never be edited.\n"
)
REFERENCE_SHA256 = "ddc6f7ec692ed0f3f7778c63283c48e8e812a78e609a9a4f79c9eda993336b11"
BACKUP_NAME = re.compile(r"data\.db\.\d{8}T\d{6}\.\d{6}Z\Z")
BACKUP_OUTPUT = re.compile(
    rb"(?<=/app-sandbox-setup-backups/)data\.db\.\d{8}T\d{6}\.\d{6}Z"
    rb"(?![A-Za-z0-9.])"
)
TABLES = ("projects", "project_sandbox_policies", "worktrees")

SMALL_DDL = """
CREATE TABLE projects (
    id TEXT PRIMARY KEY, name TEXT, main_repo_path TEXT UNIQUE,
    sandbox_enabled INTEGER NOT NULL DEFAULT 0);
CREATE TABLE project_sandbox_policies (
    project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    policy_json TEXT NOT NULL);
CREATE TABLE worktrees (
    id TEXT PRIMARY KEY, project_id TEXT, path TEXT, branch TEXT);
"""

# Copied from the existing app tests, not imported from their private helpers.
REAL_APP_DDL = """CREATE TABLE projects (
    id TEXT PRIMARY KEY NOT NULL,
    name TEXT NOT NULL,
    container_kind TEXT NOT NULL DEFAULT 'repository'
        CHECK (container_kind IN ('folder', 'repository', 'collection')),
    main_repo_path TEXT NOT NULL UNIQUE,
    default_branch TEXT NOT NULL DEFAULT 'main',
    github_owner TEXT,
    github_repo TEXT,
    github_account_id TEXT,
    tab_order INTEGER,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    last_opened_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    setup_script TEXT NOT NULL DEFAULT '',
    run_script TEXT NOT NULL DEFAULT '',
    scripts_json TEXT NOT NULL DEFAULT '',
    archive_script TEXT NOT NULL DEFAULT '',
    pull_request_prompt TEXT NOT NULL DEFAULT '',
    instructions TEXT NOT NULL DEFAULT '',
    remote_control_enabled INTEGER NOT NULL DEFAULT 0,
    server_ready_pattern TEXT NOT NULL DEFAULT '',
    auto_open_in_browser INTEGER NOT NULL DEFAULT 1,
    auto_approve INTEGER NOT NULL DEFAULT 1
, trusted_config_sha256 TEXT, trusted_config_accepted_at TEXT, branch_prefix TEXT, sparse_checkout TEXT, sandbox_enabled INTEGER NOT NULL DEFAULT 0, reusable_worktrees_enabled INTEGER NOT NULL DEFAULT 0, reusable_worktrees_max_count INTEGER NOT NULL DEFAULT 2
        CHECK (reusable_worktrees_max_count BETWEEN 1 AND 10), reusable_worktrees_expiry_days INTEGER NOT NULL DEFAULT 7
        CHECK (reusable_worktrees_expiry_days BETWEEN 1 AND 30), checkout_is_managed INTEGER NOT NULL DEFAULT 0, reusable_worktrees_user_enabled INTEGER NOT NULL DEFAULT 1, show_in_sidebar INTEGER NOT NULL DEFAULT 1, provider_pr_binding_revision TEXT NOT NULL DEFAULT '', agent_owner_session_id TEXT, copilot_account_id TEXT, copilot_account_source TEXT NOT NULL DEFAULT 'auto'
    CHECK (copilot_account_source IN ('auto', 'user')), github_account_source TEXT NOT NULL DEFAULT 'auto'
    CHECK (github_account_source IN ('auto', 'user')));
CREATE INDEX idx_projects_main_repo_path ON projects(main_repo_path);
CREATE TABLE project_sandbox_policies (
    project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    policy_json TEXT NOT NULL
);
CREATE TABLE worktrees (
    id TEXT PRIMARY KEY NOT NULL,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    branch TEXT NOT NULL,
    base_branch TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX idx_worktrees_project ON worktrees(project_id);
CREATE TRIGGER invalidate_provider_pr_badge_binding_revision
AFTER UPDATE OF provider_pr_binding_revision ON projects
WHEN OLD.provider_pr_binding_revision IS NOT NEW.provider_pr_binding_revision
BEGIN
    UPDATE workspace_pull_request_links
       SET badge_json = NULL, observed_at = NULL, scope_revision = scope_revision + 1
     WHERE workspace_id IN (SELECT id FROM workspaces WHERE project_id = NEW.id);
END;
"""


def canonical_rows(path: Path) -> str:
    """Dump all columns, retaining exact policy_json strings and stable row order."""
    if not path.exists():
        return "missing"
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        result = {}
        for table in TABLES:
            if not connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone():
                result[table] = None
                continue
            cursor = connection.execute("SELECT * FROM " + table)
            result[table] = {
                "columns": [column[0] for column in cursor.description],
                "rows": sorted(
                    [list(row) for row in cursor],
                    key=lambda row: json.dumps(row, sort_keys=True, ensure_ascii=True),
                ),
            }
        return json.dumps(result, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    finally:
        connection.close()


class Fixture:
    """All mutable inputs and outputs live under one disposable fixture root."""

    def __init__(self, container: Path, *, real_ddl: bool = False,
                 worktrees: bool = False, projects: int = 1):
        self.root = container / "fixture"
        self.home = self.root / "home"
        self.home.mkdir(parents=True)
        self.db = self.home / ".copilot/data.db"
        self.db.parent.mkdir()
        self.backups = self.db.parent / "app-sandbox-setup-backups"
        # Keep a copy of the host environment, but never inherit Git config,
        # repository selectors, template paths, or real home configuration.
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith("GIT_")}
        self.env.update(
            HOME=str(self.home), PYTHONDONTWRITEBYTECODE="1",
            DOCKER_HOST="unix://" + str(self.home / ".fixture-docker/docker.sock"),
            DOCKER_CONFIG=str(self.home / ".docker"),
            XDG_CONFIG_HOME=str(self.home / ".config"),
            GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0",
        )
        self.env.pop("DOCKER_CONTEXT", None)
        with sqlite3.connect(str(self.db)) as connection:
            connection.executescript(REAL_APP_DDL if real_ddl else SMALL_DDL)
            for index in range(1, projects + 1):
                repo = self.directory("code/repository-" + str(index))
                project_id = "p" + str(index)
                connection.execute(
                    "INSERT INTO projects(id, name, main_repo_path) VALUES (?, ?, ?)",
                    (project_id, "example-" + str(index), str(repo)),
                )
                if worktrees:
                    path = self.root / "copilot-worktrees" / ("example-" + str(index)) / "feature"
                    path.mkdir(parents=True)
                    connection.execute(
                        "INSERT INTO worktrees(id, project_id, path, branch) VALUES (?, ?, ?, ?)",
                        ("w" + str(index), project_id, str(path), "feature"),
                    )

    def directory(self, relative: str) -> Path:
        path = self.home / relative
        path.mkdir(parents=True, exist_ok=True)
        return path

    def file(self, relative: str, contents: str = "") -> Path:
        path = self.home / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")
        return path

    def policy(self, policy: object, project_id: str = "p1") -> None:
        self.raw_policy(json.dumps(policy, ensure_ascii=True), project_id)

    def raw_policy(self, raw: str, project_id: str = "p1") -> None:
        with sqlite3.connect(str(self.db)) as connection:
            connection.execute(
                "INSERT OR REPLACE INTO project_sandbox_policies VALUES (?, ?)",
                (project_id, raw),
            )

    def run(self, script: Path, args: tuple[str, ...]) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-B", str(script), *args,
             "--db", str(self.db), "--home", str(self.home)],
            cwd=str(self.root), env=self.env, capture_output=True, timeout=10,
        )

    def file_tree(self) -> tuple:
        """Include types/modes and content; ignore only generated backup names.

        Anonymous backup records retain multiplicity (counts), permissions and
        logical DB contents. SQLite file bytes themselves are not a DB contract.
        Never traverse symlinks; record their targets instead.
        """
        entries = []
        anonymous_backups = []

        def visit(path: Path) -> None:
            info = path.lstat()
            metadata = (stat.S_IFMT(info.st_mode), stat.S_IMODE(info.st_mode))
            if stat.S_ISLNK(info.st_mode):
                content = ("symlink", os.readlink(str(path)))
            elif stat.S_ISREG(info.st_mode):
                is_backup = path.parent == self.backups and BACKUP_NAME.fullmatch(path.name)
                content = (("db", canonical_rows(path)) if path == self.db or is_backup
                           else ("sha256", hashlib.sha256(path.read_bytes()).hexdigest()))
            else:
                content = None
            record = (metadata, content)
            if path.parent == self.backups and BACKUP_NAME.fullmatch(path.name):
                anonymous_backups.append(record)
            else:
                entries.append((path.relative_to(self.root).as_posix(), record))
            if stat.S_ISDIR(info.st_mode):
                for child in sorted(path.iterdir()):
                    visit(child)

        visit(self.root)
        return tuple(entries), tuple(sorted(anonymous_backups))

    def capture(self, result: subprocess.CompletedProcess) -> dict:
        # Capture file state before opening the DB for the canonical row dump.
        tree = self.file_tree()
        return {
            "exit": result.returncode,
            "stdout": BACKUP_OUTPUT.sub(b"data.db.<timestamp>", result.stdout),
            "stderr": BACKUP_OUTPUT.sub(b"data.db.<timestamp>", result.stderr),
            "db": canonical_rows(self.db),
            "tree": tree,
        }


class AppSandboxSetupEquivalenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="app-sandbox-equivalence-")
        self.addCleanup(self.temporary.cleanup)
        self.container = Path(self.temporary.name).resolve()

    def fixture(self, **options) -> Fixture:
        root = self.container / "fixture"
        if root.exists():
            shutil.rmtree(root)
        return Fixture(self.container, **options)

    def equivalent(self, fixture: Fixture, *args: str, expected: int = 0) -> dict:
        """Run both sides from identical bytes at identical absolute paths.

        Snapshot even read commands: a regression that starts writing must not
        contaminate the second run or be hidden by running it on oracle state.
        Leave live results in place for apply→plan and rollback sequences.
        """
        snapshot = self.container / "snapshot"
        shutil.copytree(fixture.root, snapshot, symlinks=True)
        try:
            oracle_result = fixture.run(REFERENCE, args)
            oracle = fixture.capture(oracle_result)
            shutil.rmtree(fixture.root)
            shutil.copytree(snapshot, fixture.root, symlinks=True)
            live = fixture.capture(fixture.run(LIVE, args))
            with self.subTest(command=args):
                self.assertEqual(oracle, live)
                self.assertEqual(expected, oracle_result.returncode, oracle_result.stdout)
            return oracle
        finally:
            shutil.rmtree(snapshot)

    def plan_digest(self, fixture: Fixture, *flags: str) -> str:
        # This is the ORACLE's digest, not a digest computed by the live script.
        output = self.equivalent(fixture, "plan", "--json", *flags)["stdout"]
        digest = json.loads(output)["digest"]
        self.assertRegex(digest, r"^[0-9a-f]{64}$")
        return digest

    def apply_then_plan(self, fixture: Fixture, *flags: str, json_mode: bool = False) -> None:
        digest = self.plan_digest(fixture, *flags)
        output_flags = ("--json",) if json_mode else ()
        self.equivalent(fixture, "apply", "--confirm", digest, *flags, *output_flags)
        self.equivalent(fixture, "plan", *flags, *output_flags)

    def test_reference_is_frozen_except_for_its_three_line_header(self) -> None:
        reference = REFERENCE.read_bytes()
        prefix = (
            b"#!/usr/bin/env python3\n"
            b'"""Plan and confirm portable GitHub Copilot desktop sandbox settings."""\n'
        )
        self.assertTrue(reference.startswith(prefix + REFERENCE_HEADER))
        original = prefix + reference[len(prefix + REFERENCE_HEADER):]
        # Pin only the oracle; do NOT compare with LIVE, which the next slice changes.
        self.assertEqual(REFERENCE_SHA256, hashlib.sha256(original).hexdigest())

    def test_fresh_projects_with_and_without_worktrees(self) -> None:
        for worktrees in (False, True):
            with self.subTest(worktrees=worktrees):
                fixture = self.fixture(worktrees=worktrees, projects=2)
                self.equivalent(fixture, "plan")
                self.equivalent(fixture, "guide")
                self.equivalent(fixture, "apply", "--confirm", "wrong", expected=4)
                self.apply_then_plan(fixture)
                # Reapplying must also have identical no-op/backup behaviour.
                if not worktrees:
                    self.apply_then_plan(fixture, json_mode=True)

    def test_real_app_ddl_and_reversible_rollback(self) -> None:
        fixture = self.fixture(real_ddl=True, worktrees=True, projects=2)
        self.equivalent(fixture, "plan")
        self.equivalent(fixture, "guide")
        self.apply_then_plan(fixture, json_mode=True)
        backup = next(fixture.backups.iterdir())
        preview = self.equivalent(fixture, "rollback", "--from", str(backup))
        digest = re.search(rb"Plan digest: ([0-9a-f]{64})", preview["stdout"]).group(1).decode("ascii")
        json_preview = self.equivalent(fixture, "rollback", "--from", str(backup), "--json")
        self.assertEqual(digest, json.loads(json_preview["stdout"])["digest"])
        self.equivalent(
            fixture, "rollback", "--from", str(backup), "--confirm", "wrong", expected=4,
        )
        self.equivalent(fixture, "rollback", "--from", str(backup), "--confirm", digest)
        self.equivalent(fixture, "rollback", "--from", str(backup), "--json")
        self.equivalent(fixture, "plan", "--json")

    def test_existing_policy_user_values_invalid_entries_and_conflicts(self) -> None:
        fixture = self.fixture(worktrees=True)
        for relative in (".config/git", "user-rw", "user-ro", "user-denied", ".ssh"):
            fixture.directory(relative)
        fixture.file(".ssh/synthetic-marker", "not a key")
        fixture.policy({
            "readwritePaths": [
                str(fixture.home), str(fixture.home / "user-rw"),
                str(fixture.home / "user-rw"), "relative", "/invalid\nentry",
                str(fixture.home / ".config/git"), str(fixture.home / ".ssh"),
            ],
            "readonlyPaths": [str(fixture.home / "user-ro"), "relative"],
            "deniedPaths": [
                str(fixture.home / "user-denied"), str(fixture.home / ".config"),
                str(fixture.home / "code"), "relative", "/invalid\x7fentry",
            ],
            "allowOutbound": False, "allowLocalNetwork": False,
            "allowGitCredentials": True, "allowGhCredentials": False,
            "unknown": {"nested": ["synthetic-user-value", 7, True]},
        })
        self.equivalent(fixture, "plan")
        self.equivalent(fixture, "guide")
        self.apply_then_plan(fixture)
        self.apply_then_plan(fixture, "--mask-credentials", json_mode=True)
        self.apply_then_plan(fixture, "--no-mask-credentials", json_mode=True)

    def test_old_applied_policy_retirement(self) -> None:
        fixture = self.fixture()
        old_rw = (".copilot/session-state", "Library/Application Support/Google/Chrome for Testing")
        for relative in old_rw:
            fixture.directory(relative)
        # Wrong types remain non-qualifying even when HOME is under a /tmp grant.
        fixture.file(".azure")
        fixture.directory(".netrc")
        fixture.policy({
            "readwritePaths": [str(fixture.home / path) for path in old_rw],
            "readonlyPaths": [],
            "deniedPaths": [str(fixture.home / path) for path in (
                ".copilot/data.db-wal", ".copilot/data.db-shm", ".azure", ".netrc",
                "user-denied",
            )],
            "allowOutbound": True, "allowLocalNetwork": True,
            "allowGitCredentials": False, "allowGhCredentials": False,
        })
        self.equivalent(fixture, "plan")
        self.apply_then_plan(fixture, json_mode=True)

    def test_placeholder_directories(self) -> None:
        fixture = self.fixture()
        for relative in (".netrc", ".aws", ".config/op"):
            fixture.directory(relative)
        fixture.policy({"readwritePaths": [str(fixture.home / ".config")]})
        self.equivalent(fixture, "plan")
        self.apply_then_plan(fixture, json_mode=True)

    def test_corrupt_policy_isolated_to_one_of_two_projects(self) -> None:
        fixture = self.fixture(projects=2)
        fixture.raw_policy('{"readwritePaths": [false]}', "p2")
        self.equivalent(fixture, "plan")
        self.equivalent(fixture, "guide")
        self.apply_then_plan(fixture, json_mode=True)

    def test_schema_missing_db_and_no_projects_exit_codes(self) -> None:
        for failure, code in (("schema", 3), ("missing-db", 2), ("no-projects", 1)):
            with self.subTest(failure=failure):
                fixture = self.fixture()
                if failure == "missing-db":
                    fixture.db.unlink()
                else:
                    with sqlite3.connect(str(fixture.db)) as connection:
                        connection.execute(
                            "DROP TABLE worktrees" if failure == "schema" else "DELETE FROM projects"
                        )
                for command in (("plan",), ("plan", "--json"), ("guide",),
                                ("apply", "--confirm", "wrong")):
                    self.equivalent(fixture, *command, expected=code)

    def rich_tools(self, fixture: Fixture) -> None:
        for relative in (
            ".gradle", ".m2", ".config/git", ".fixture-docker",
            "Library/Caches/copilot/pkg", "Library/Caches/copilot/mcp",
            "Library/Caches/copilot-desktop-gh-x.y",
            "Library/Java/JavaVirtualMachines/temurin-21/Contents/Home", "git-config/hooks",
        ):
            fixture.directory(relative)
        fixture.file(
            ".docker/config.json",
            '{"auths":{"fixture.invalid":{"auth":"synthetic-not-a-credential"}}}',
        )
        fixture.file(".config/gh/hosts.yml",
                     "fixture.invalid:\n  oauth_token: synthetic-not-a-credential\n")
        fixture.file("git-config/included", "[core]\n  autocrlf = false\n")
        fixture.file("git-config/excludes", "*.fixture\n")
        fixture.file(
            ".gitconfig",
            "[include]\n  path = git-config/included\n"
            "[core]\n  hooksPath = ~/git-config/hooks\n  excludesfile = ~/git-config/excludes\n"
            "[commit]\n  gpgsign = true\n",
        )
        for suffix in (".open-lock", "-wal", "-shm", ".pre-update-backup-fixture",
                       ".before-sandbox-setup-fixture"):
            fixture.file(".copilot/data.db" + suffix)

    def test_tool_presence_and_flag_matrix(self) -> None:
        for flags in (
            (), ("--mask-credentials",), ("--no-mask-credentials",), ("--no-docker",),
            ("--mask-credentials", "--no-docker"), ("--no-mask-credentials", "--no-docker"),
        ):
            with self.subTest(flags=flags):
                fixture = self.fixture(worktrees=True)
                self.rich_tools(fixture)
                self.equivalent(fixture, "plan", *flags)
                if not flags:
                    self.equivalent(fixture, "guide")
                self.apply_then_plan(fixture, *flags, json_mode=True)

    def test_project_ssh_remote(self) -> None:
        git = shutil.which("git")
        if git is None:
            self.skipTest("git is unavailable; only the SSH remote subcase is skipped")
        fixture = self.fixture()
        repo = fixture.home / "code/repository-1"
        for args in (("init", "-q", str(repo)),
                     ("-C", str(repo), "remote", "add", "origin", "git@fixture.invalid:team/repo")):
            subprocess.run([git, *args], cwd=str(fixture.root), env=fixture.env,
                           check=True, capture_output=True, timeout=10)
        self.equivalent(fixture, "plan")
        self.equivalent(fixture, "guide")
        self.apply_then_plan(fixture, json_mode=True)

    def test_git_unavailable(self) -> None:
        fixture = self.fixture()
        fixture.env["PATH"] = str(fixture.directory("empty-bin"))
        self.equivalent(fixture, "plan")
        self.apply_then_plan(fixture, json_mode=True)


if __name__ == "__main__":
    unittest.main()
