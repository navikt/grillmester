from __future__ import annotations

import contextlib
import errno
import importlib.util
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "plugin/skills/app-sandbox-setup/scripts/app_sandbox_setup.py"
)

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


class AppSandboxSetupTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.home = self.root / "home"
        self.home.mkdir()
        (self.home / "code/repository").mkdir(parents=True)
        self.db = self.home / ".copilot/data.db"
        self.db.parent.mkdir()
        environment = mock.patch.dict(os.environ, {
            "HOME": str(self.home), "DOCKER_HOST": "unix://" + str(self.home / ".fixture-docker/docker.sock"),
        })
        environment.start()
        self.addCleanup(environment.stop)
        with sqlite3.connect(str(self.db)) as connection:
            connection.executescript("""
                CREATE TABLE projects (
                    id TEXT PRIMARY KEY, name TEXT, main_repo_path TEXT UNIQUE,
                    sandbox_enabled INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE project_sandbox_policies (
                    project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
                    policy_json TEXT NOT NULL);
                CREATE TABLE worktrees (id TEXT PRIMARY KEY, project_id TEXT, path TEXT, branch TEXT);
            """)
            connection.execute(
                "INSERT INTO projects(id, name, main_repo_path) VALUES (?, ?, ?)",
                ("p1", "example", str(self.home / "code/repository")),
            )
        spec = importlib.util.spec_from_file_location("app_sandbox_setup", SCRIPT)
        assert spec and spec.loader
        self.app = importlib.util.module_from_spec(spec)
        # Importing must not leave __pycache__ in the manifested plugin tree.
        with mock.patch.object(sys, "dont_write_bytecode", True):
            spec.loader.exec_module(self.app)
        # macOS TMPDIR lives below /private/var, unlike real developer homes.
        # Keep temporary fixtures there while retaining all other system guards.
        if hasattr(self.app, "SYSTEM_AREAS"):
            self.app.SYSTEM_AREAS = tuple(
                path for path in self.app.SYSTEM_AREAS if path not in ("/private", "/var")
            )

    def run_cli(self, command: str, *options: str) -> tuple[int, str]:
        output = io.StringIO()
        with mock.patch.dict(os.environ, {"HOME": str(self.home),
                                         "DOCKER_HOST": "unix://" + str(self.home / ".fixture-docker/docker.sock")}), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = self.app.main([
                command, "--db", str(self.db), "--home", str(self.home), *options,
            ])
        return code, output.getvalue()

    def test_plan_is_read_only_and_prints_diff_and_digest(self) -> None:
        before = self.db.read_bytes(), self.db.stat().st_mtime_ns
        code, output = self.run_cli("plan")
        self.assertEqual(0, code, output)
        connection = self.app.open_db(self.db)
        self.addCleanup(connection.close)
        self.assertEqual(1, connection.execute("PRAGMA query_only").fetchone()[0])
        self.assertIn("example", output)
        self.assertIn(f'+ readwritePaths: "{self.home / "code"}"', output)
        self.assertIn("sandbox_enabled: 0 -> 1", output)
        self.assertRegex(output, r"Plan digest: [0-9a-f]{64}")
        self.assertEqual(before, (self.db.read_bytes(), self.db.stat().st_mtime_ns))
        self.assertEqual(["data.db"], [p.name for p in self.db.parent.iterdir()])

    def test_closed_wal_db_can_be_planned_without_sidecars(self) -> None:
        with sqlite3.connect(str(self.db)) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
        connection.close()
        self.assertFalse(Path(str(self.db) + "-wal").exists())
        code, output = self.run_cli("plan")
        self.assertEqual(0, code, output)

    def digest(self, *options: str) -> str:
        code, output = self.run_cli("plan", *options)
        self.assertEqual(0, code, output)
        return re.search(r"Plan digest: ([0-9a-f]{64})", output).group(1)

    def policies(self) -> list[dict]:
        with sqlite3.connect(str(self.db)) as connection:
            return [
                json.loads(row[0])
                for row in connection.execute("SELECT policy_json FROM project_sandbox_policies ORDER BY project_id")
            ]

    def set_policy(self, policy: object) -> None:
        with sqlite3.connect(str(self.db)) as connection:
            connection.execute(
                "INSERT OR REPLACE INTO project_sandbox_policies VALUES (?, ?)",
                ("p1", json.dumps(policy)),
            )

    def test_merge_keeps_user_policy_but_denies_sensitive_paths(self) -> None:
        denied = str(self.home / ".ssh")
        self.set_policy({
            "readwritePaths": ["/custom/rw", "/custom/rw", denied],
            "readonlyPaths": ["/custom/ro", denied],
            "deniedPaths": ["/custom/denied"],
            "custom": {"keep": "unchanged"},
            "allowOutbound": False,
        })
        (self.home / ".gradle").mkdir()
        code, output = self.run_cli("apply", "--confirm", self.digest())
        self.assertEqual(0, code, output)
        policy = self.policies()[0]
        self.assertEqual("/custom/rw", policy["readwritePaths"][0])
        self.assertEqual(1, policy["readwritePaths"].count("/custom/rw"))
        self.assertEqual("/custom/ro", policy["readonlyPaths"][0])
        self.assertEqual("/custom/denied", policy["deniedPaths"][0])
        self.assertEqual({"keep": "unchanged"}, policy["custom"])
        for relative in (
            ".ssh", ".aws", ".gnupg", ".kube", ".config/gcloud", "Library/Keychains",
            ".netrc", ".copilot/data.db", ".copilot/data.db-wal", ".copilot/data.db-shm",
            ".copilot/app-sandbox-setup-backups", ".copilot/settings.json",
            ".copilot/config.json", ".copilot/mcp-oauth-config",
        ):
            self.assertIn(str(self.home / relative), policy["deniedPaths"])
        self.assertNotIn(denied, policy["readwritePaths"])
        self.assertNotIn(denied, policy["readonlyPaths"])
        self.assertIn("removed", output)
        self.assertIn(str(self.home / ".gradle"), policy["readwritePaths"])
        self.assertNotIn(str(self.home / ".m2"), policy["readwritePaths"])
        self.assertIn("skipped (missing; rerun after installing)", output)
        self.assertTrue(policy["allowOutbound"])
        self.assertTrue(policy["allowLocalNetwork"])
        self.assertFalse(policy["allowGitCredentials"])
        self.assertFalse(policy["allowGhCredentials"])
        self.assertIn("exfiltrate", output)

    def test_code_roots_are_safe_resolved_and_shared_across_projects(self) -> None:
        link = self.root / "home-link"
        link.symlink_to(self.home, target_is_directory=True)
        paths = (
            ("p1", str(link / "repository")),
            ("p2", str(self.root / "repository")),
            ("p3", "/opt/repository"),
            ("p4", "relative/repository"),
            ("p5", "/Volumes/team/code/repository"),
            ("p6", str(self.home / "bad\nrepository")),
        )
        for _, raw in paths:
            if raw.startswith(str(self.root)):
                Path(raw).mkdir(parents=True, exist_ok=True)
        for relative in ("copilot-worktrees/team/branch", "team/worktree"):
            (self.home / relative).mkdir(parents=True)
        with sqlite3.connect(str(self.db)) as connection:
            connection.execute("DELETE FROM projects")
            connection.executemany(
                "INSERT INTO projects(id, name, main_repo_path) VALUES (?, ?, ?)",
                [(identifier, identifier, path) for identifier, path in paths],
            )
            connection.execute(
                "INSERT INTO worktrees VALUES (?, ?, ?, ?)",
                ("w1", "p1", str(self.home / "copilot-worktrees/team/branch"), "branch"),
            )
            connection.execute(
                "INSERT INTO worktrees VALUES (?, ?, ?, ?)",
                ("w2", "p1", str(self.home / "team/worktree"), "branch"),
            )
        code, output = self.run_cli("apply", "--confirm", self.digest())
        self.assertEqual(0, code, output)
        for policy in self.policies():
            roots = policy["readwritePaths"]
            self.assertIn(str(self.home / "repository"), roots)
            self.assertIn(str(self.root / "repository"), roots)
            self.assertIn(str(self.home / "copilot-worktrees"), roots)
            self.assertIn(str(self.home / "team/worktree"), roots)
            self.assertIn("/Volumes/team/code", roots)
            for unsafe in (str(self.home), str(self.root), str(link), "/opt", "/opt/repository"):
                self.assertNotIn(unsafe, roots)
            self.assertFalse(any("\n" in path or not Path(path).is_absolute() for path in roots))
        self.assertIn("unsafe", output)
        self.assertIn("non-absolute", output)
        self.assertIn("control", output)

    def test_invalid_policy_fails_safe_without_echoing_unknown_content(self) -> None:
        for policy in (
            [], None, "not-an-object", {"readwritePaths": "not-a-list"},
            {"readonlyPaths": [1]}, {"deniedPaths": None},
            {"allowOutbound": 1}, {"allowLocalNetwork": "true"},
            {"allowGhCredentials": None}, {"allowGitCredentials": []},
        ):
            with self.subTest(policy=policy):
                self.set_policy(policy)
                before = self.db.read_bytes()
                for command in ("plan", "apply"):
                    code, output = self.run_cli(command, *(("--confirm", self.digest()) if command == "apply" else ()))
                    self.assertEqual(0, code, output)
                    self.assertIn("example: corrupt policy skipped", output)
                    self.assertEqual(before, self.db.read_bytes())
        with sqlite3.connect(str(self.db)) as connection:
            connection.execute("UPDATE project_sandbox_policies SET policy_json = ?", ("{private invalid",))
        code, output = self.run_cli("plan")
        self.assertEqual(0, code, output)
        self.assertNotIn("private invalid", output)

    def test_corrupt_project_does_not_block_valid_project_and_is_digest_bound(self) -> None:
        self.set_policy([])
        with sqlite3.connect(str(self.db)) as connection:
            connection.execute("INSERT INTO projects(id, name, main_repo_path) VALUES ('p2', 'valid', '/Volumes/offline/repo')")
        old_digest = self.digest()
        code, output = self.run_cli("apply", "--confirm", old_digest)
        self.assertEqual(0, code, output)
        with sqlite3.connect(str(self.db)) as connection:
            self.assertEqual([("p1", 0), ("p2", 1)], connection.execute(
                "SELECT id, sandbox_enabled FROM projects ORDER BY id").fetchall())
        with self.app.open_db(self.db) as connection:
            plan = self.app.compute_plan(connection, self.home, None)
            self.assertEqual(["p1"], plan["skipped"])

    def test_schema_mismatch_is_read_only_and_returns_guide_fallback(self) -> None:
        with sqlite3.connect(str(self.db)) as connection:
            connection.execute("DROP TABLE worktrees")
        before = self.db.read_bytes(), self.db.stat().st_mtime_ns
        for command in ("plan", "apply"):
            code, output = self.run_cli(command, *(("--confirm", "0" * 64) if command == "apply" else ()))
            self.assertEqual(3, code, output)
            self.assertIn("guide", output)
            self.assertEqual(before, (self.db.read_bytes(), self.db.stat().st_mtime_ns))
        self.assertFalse((self.db.parent / "app-sandbox-setup-backups").exists())

    def test_real_app_schema_plan_apply_plan_does_not_fire_badge_trigger(self) -> None:
        with sqlite3.connect(str(self.db)) as connection:
            connection.executescript("""
                DROP TABLE project_sandbox_policies;
                DROP TABLE worktrees;
                DROP TABLE projects;
                CREATE TABLE workspaces (id TEXT PRIMARY KEY, project_id TEXT);
                CREATE TABLE workspace_pull_request_links (
                    workspace_id TEXT, badge_json TEXT, observed_at TEXT, scope_revision INTEGER);
            """)
            connection.executescript(REAL_APP_DDL)
            connection.execute(
                "INSERT INTO projects(id, name, main_repo_path) VALUES (?, ?, ?)",
                ("p1", "example", str(self.home / "code/repository")),
            )
            connection.execute("INSERT INTO workspaces VALUES ('ws1', 'p1')")
            connection.execute(
                "INSERT INTO workspace_pull_request_links VALUES (?, ?, ?, ?)",
                ("ws1", '{"fixture":true}', "fixture-observation", 7),
            )
            before_links = connection.execute("SELECT * FROM workspace_pull_request_links").fetchall()

        digest = self.digest()
        code, output = self.run_cli("apply", "--confirm", digest)
        self.assertEqual(0, code, output)
        self.assertEqual(1, len(self.policies()))
        code, output = self.run_cli("plan")
        self.assertEqual(0, code, output)
        self.assertIn("no changes", output)
        with sqlite3.connect(str(self.db)) as connection:
            self.assertEqual((1, ""), connection.execute(
                "SELECT sandbox_enabled, provider_pr_binding_revision FROM projects"
            ).fetchone())
            self.assertEqual(
                before_links, connection.execute("SELECT * FROM workspace_pull_request_links").fetchall(),
            )
            # Prove the fixture trigger is active, but only for its own UPDATE OF column.
            connection.execute("UPDATE projects SET provider_pr_binding_revision = 'fixture-revision'")
            self.assertEqual(
                [("ws1", None, None, 8)],
                connection.execute("SELECT * FROM workspace_pull_request_links").fetchall(),
            )

    def test_write_relevant_triggers_are_rejected_without_changes(self) -> None:
        headers = (
            "AFTER INSERT ON project_sandbox_policies",
            "BEFORE UPDATE OF policy_json ON project_sandbox_policies",
            "AFTER DELETE ON project_sandbox_policies",
            "AFTER UPDATE ON projects",
            "BEFORE UPDATE OF name, sandbox_enabled ON projects",
            'aFtEr\nUpDaTe Of "name", "SANDBOX_ENABLED"\nOn "projects"',
            "BEFORE UPDATE OF [sandbox_enabled], [name] ON [projects]",
            "AFTER UPDATE OF `sandbox_enabled` ON `projects`",
            "AFTER UPDATE OF 'sandbox_enabled' ON 'projects'",
        )
        for header in headers:
            with self.subTest(header=header):
                digest = self.digest()
                with sqlite3.connect(str(self.db)) as connection:
                    connection.execute(
                        f"CREATE TRIGGER fixture_trigger {header} "
                        "BEGIN SELECT RAISE(ABORT, 'fixture-trigger-fired'); END"
                    )
                before = self.db.read_bytes(), self.db.stat().st_mtime_ns
                for command in ("plan", "apply"):
                    code, output = self.run_cli(
                        command, *(("--confirm", digest) if command == "apply" else ()),
                    )
                    self.assertEqual(3, code, output)
                    self.assertIn("guide", output)
                    self.assertNotIn("fixture-trigger-fired", output)
                    self.assertEqual(before, (self.db.read_bytes(), self.db.stat().st_mtime_ns))
                    self.assertFalse((self.db.parent / "app-sandbox-setup-backups").exists())
                with sqlite3.connect(str(self.db)) as connection:
                    connection.execute("DROP TRIGGER fixture_trigger")

    def test_unparseable_trigger_header_is_rejected_without_changes(self) -> None:
        digest = self.digest()
        with sqlite3.connect(str(self.db)) as connection:
            # SQLite accepts comments here; the deliberately small parser fails closed.
            connection.execute("""
                CREATE TRIGGER fixture_trigger AFTER UPDATE /* header comment */ OF name
                ON projects BEGIN SELECT 1; END
            """)
        before = self.db.read_bytes(), self.db.stat().st_mtime_ns
        for command in ("plan", "apply"):
            code, output = self.run_cli(
                command, *(("--confirm", digest) if command == "apply" else ()),
            )
            self.assertEqual(3, code, output)
            self.assertEqual(before, (self.db.read_bytes(), self.db.stat().st_mtime_ns))
        self.assertFalse((self.db.parent / "app-sandbox-setup-backups").exists())

    def test_unrelated_project_and_worktree_triggers_are_allowed_and_do_not_fire(self) -> None:
        headers = (
            "AFTER INSERT ON projects",
            "BEFORE DELETE ON projects",
            "AFTER UPDATE OF name ON projects",
            'aFtEr\nUpDaTe Of "NAME", [main_repo_path]\nOn "projects"',
            "UPDATE OF `name` ON `projects`",
            "AFTER UPDATE OF 'name' ON 'projects'",
            # Commas and escaped quotes inside identifiers are not column separators.
            'AFTER UPDATE OF "name,sandbox_enabled", "na""me" ON projects',
            "AFTER UPDATE OF `na``me`, 'na''me' ON projects",
            "AFTER INSERT ON worktrees",
            "BEFORE UPDATE ON worktrees",
            "AFTER DELETE ON worktrees",
        )
        with sqlite3.connect(str(self.db)) as connection:
            connection.execute("CREATE TABLE trigger_events (event TEXT)")
            connection.execute(
                "INSERT INTO worktrees VALUES (?, ?, ?, ?)",
                ("w1", "p1", str(self.home / "worktrees/example/branch"), "branch"),
            )
            before_worktrees = connection.execute("SELECT * FROM worktrees").fetchall()
        for header in headers:
            with self.subTest(header=header):
                with sqlite3.connect(str(self.db)) as connection:
                    connection.execute("UPDATE projects SET sandbox_enabled = 0")
                    connection.execute("DELETE FROM project_sandbox_policies")
                    connection.execute(
                        f'CREATE TRIGGER "fixture "" ON trigger" {header} '
                        "BEGIN INSERT INTO trigger_events VALUES ('sandbox_enabled'); END"
                    )
                code, output = self.run_cli("apply", "--confirm", self.digest())
                self.assertEqual(0, code, output)
                self.assertEqual(1, len(self.policies()))
                code, output = self.run_cli("plan")
                self.assertEqual(0, code, output)
                self.assertIn("no changes", output)
                with sqlite3.connect(str(self.db)) as connection:
                    self.assertEqual((1,), connection.execute(
                        "SELECT sandbox_enabled FROM projects"
                    ).fetchone())
                    self.assertEqual([], connection.execute("SELECT * FROM trigger_events").fetchall())
                    self.assertEqual(
                        before_worktrees, connection.execute("SELECT * FROM worktrees").fetchall(),
                    )
                    connection.execute('DROP TRIGGER "fixture "" ON trigger"')

    def test_composite_project_key_is_rejected_as_schema_mismatch(self) -> None:
        with sqlite3.connect(str(self.db)) as connection:
            connection.executescript("""
                DROP TABLE project_sandbox_policies;
                DROP TABLE projects;
                CREATE TABLE projects (
                    id TEXT, name TEXT, main_repo_path TEXT UNIQUE,
                    sandbox_enabled INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(id, name));
                CREATE TABLE project_sandbox_policies (
                    project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
                    policy_json TEXT NOT NULL);
            """)
        before = self.db.read_bytes()
        code, output = self.run_cli("plan")
        self.assertEqual(3, code, output)
        self.assertEqual(before, self.db.read_bytes())

    def test_digest_mismatch_on_concurrent_change_or_masking_writes_nothing(self) -> None:
        digest = self.digest()
        self.set_policy({"custom": {"concurrent": True}})
        before = self.db.read_bytes()
        code, output = self.run_cli("apply", "--confirm", digest)
        self.assertEqual(4, code, output)
        self.assertEqual(before, self.db.read_bytes())
        code, output = self.run_cli("apply", "--confirm", self.digest(), "--mask-credentials")
        self.assertEqual(4, code, output)
        self.assertEqual(before, self.db.read_bytes())
        self.assertFalse((self.db.parent / "app-sandbox-setup-backups").exists())

    def test_missing_or_unreadable_db_returns_2_without_creating_it(self) -> None:
        self.db.unlink()
        code, output = self.run_cli("plan")
        self.assertEqual(2, code, output)
        self.assertIn("app never started or wrong --db", output)
        self.assertFalse(self.db.exists())
        self.db.mkdir()
        code, output = self.run_cli("plan")
        self.assertEqual(2, code, output)
        with mock.patch.object(self.app.sqlite3, "connect", side_effect=PermissionError("private fixture")):
            code, output = self.run_cli("apply", "--confirm", "0" * 64)
        self.assertEqual(2, code, output)
        self.assertNotIn("private fixture", output)
        self.assertIn("Run outside the sandbox", output)

    def test_busy_db_returns_5(self) -> None:
        connection = sqlite3.connect(str(self.db))
        self.addCleanup(connection.close)
        connection.execute("BEGIN IMMEDIATE")
        code, output = self.run_cli("apply", "--confirm", "0" * 64)
        self.assertEqual(5, code, output)
        self.assertIn("busy", output)

    @unittest.skipIf(os.geteuid() == 0, "root bypasses chmod permissions")
    def test_denied_db_returns_2_without_disclosing_errors(self) -> None:
        self.db.chmod(0)
        try:
            code, output = self.run_cli("plan")
            self.assertEqual(2, code, output)
            self.assertIn("sandbox is ON", output)
        finally:
            self.db.chmod(0o600)

    def test_mask_credentials_sets_both_flags_and_warns_about_loopback(self) -> None:
        code, output = self.run_cli("apply", "--mask-credentials", "--confirm", self.digest("--mask-credentials"))
        self.assertEqual(0, code, output)
        policy = self.policies()[0]
        self.assertTrue(policy["allowGitCredentials"])
        self.assertTrue(policy["allowGhCredentials"])
        self.assertTrue(policy["allowLocalNetwork"])
        self.assertIn("loopback deny", output)

    def test_hardening_retires_old_session_grant_and_discovers_app_caches(self) -> None:
        relatives = (
            ".config/git", ".config/fish", ".config/mise", ".gradle/init.d",
            ".docker/cli-plugins", "Library/Caches/copilot", "Library/Caches/copilot/pkg",
            "Library/Caches/copilot/mcp", "Library/Caches/copilot/keep",
            "Library/Caches/github-copilot-git-fixture", "Library/Caches/copilot-desktop-fixture",
        )
        for relative in relatives:
            (self.home / relative).mkdir(parents=True)
        (self.home / "Library/Caches/copilot/state.json").touch()
        writable = mock.patch.object(self.app, "APP_CACHE_WRITABLE", {"keep"})
        writable.start()
        self.addCleanup(writable.stop)
        self.set_policy({"readwritePaths": [
            str(self.home / ".copilot/session-state"), str(self.home / ".config/git"),
            str(self.home / "Library/Caches/copilot"),
        ]})
        code, output = self.run_cli("apply", "--confirm", self.digest())
        self.assertEqual(0, code, output)
        policy = self.policies()[0]
        for relative in relatives:
            path = str(self.home / relative)
            if relative.endswith("/keep"):
                self.assertNotIn(path, policy["readonlyPaths"])
                self.assertIn(path, policy["readwritePaths"])
            else:
                self.assertIn(path, policy["readonlyPaths"])
        self.assertNotIn(str(self.home / ".copilot/session-state"), policy["readwritePaths"])
        self.assertNotIn(str(self.home / ".config/git"), policy["readwritePaths"])
        self.assertNotIn(str(self.home / "Library/Caches/copilot"), policy["readwritePaths"])
        self.assertIn("retired", output)
        self.assertIn("app update", output)
        code, output = self.run_cli("plan")
        self.assertEqual(0, code, output)
        self.assertIn("no changes", output)

    def test_copilot_cache_root_requires_directory_and_is_readonly_probe_target(self) -> None:
        copilot = self.home / "Library/Caches/copilot"
        copilot.parent.mkdir(parents=True)
        for state in ("missing", "file", "directory"):
            with self.subTest(state=state):
                if state == "file":
                    copilot.touch()
                elif state == "directory":
                    copilot.unlink()
                    copilot.mkdir()
                code, output = self.run_cli("plan", "--json")
                self.assertEqual(0, code, output)
                added = json.loads(output)["projects"][0]["diff"]["readonlyPaths"]["added"]
                self.assertEqual(state == "directory", str(copilot) in added)
        code, repeated = self.run_cli("plan", "--json")
        self.assertEqual(0, code, repeated)
        self.assertEqual(output, repeated)
        before = set(self.home.rglob("*")), self.db.read_bytes()
        with mock.patch.object(self.app, "probe_write", wraps=self.app.probe_write) as write, \
                mock.patch.object(self.app, "probe_loopback", return_value="OK"):
            probes = self.app.behavioral_probes(self.home, self.db)
        self.assertEqual("OK", probes["readonly write"])
        self.assertEqual(copilot, write.call_args_list[-1].args[0])
        self.assertEqual(before, (set(self.home.rglob("*")), self.db.read_bytes()))

    def test_tool_setups_and_docker_opt_out(self) -> None:
        ro = ("Library/Java/JavaVirtualMachines", ".sdkman", ".asdf", ".jenv",
              ".volta", ".pyenv", ".rustup", ".local/bin",
              "Library/Application Support/fnm", ".npmrc", ".yarnrc.yml")
        rw = ("Library/Application Support/kotlin", ".konan", ".testcontainers.properties",
              ".colima", ".orbstack", ".lima", "go", ".cargo", ".yarn", ".rd", ".docker",
              ".fixture-docker")
        for relative in ro + rw:
            (self.home / relative).mkdir(parents=True)
        code, output = self.run_cli("apply", "--confirm", self.digest())
        self.assertEqual(0, code, output)
        policy = self.policies()[0]
        for relative in ro:
            self.assertIn(str(self.home / relative), policy["readonlyPaths"])
        for relative in rw:
            self.assertIn(str(self.home / relative), policy["readwritePaths"])
        code, output = self.run_cli("apply", "--no-docker", "--confirm", self.digest("--no-docker"))
        self.assertEqual(0, code, output)
        for relative in (".rd", ".docker", ".colima", ".orbstack", ".lima",
                         ".fixture-docker", ".testcontainers.properties"):
            self.assertNotIn(str(self.home / relative), self.policies()[0]["readwritePaths"])
        self.assertIn("Testcontainers/docker will not work", output)

    def test_unsafe_parents_fall_back_and_copilot_and_missing_paths_are_skipped(self) -> None:
        relatives = ("Downloads/repo", "Desktop/repo", "Documents/repo",
                     "Library/Mobile Documents/repo", ".config/repo", ".copilot/worktrees/repo")
        for index, relative in enumerate(relatives):
            path = self.home / relative
            path.mkdir(parents=True)
            with sqlite3.connect(str(self.db)) as connection:
                connection.execute("INSERT INTO worktrees VALUES (?, 'p1', ?, 'branch')",
                                   (str(index), str(path)))
        with sqlite3.connect(str(self.db)) as connection:
            connection.execute("INSERT INTO worktrees VALUES ('missing', 'p1', ?, 'branch')",
                               (str(self.home / "missing/repo"),))
            connection.execute("INSERT INTO worktrees VALUES ('disk', 'p1', '/Volumes/offline/team/repo', 'branch')")
        code, output = self.run_cli("apply", "--confirm", self.digest())
        self.assertEqual(0, code, output)
        rw = self.policies()[0]["readwritePaths"]
        for relative in relatives[:-1]:
            self.assertIn(str(self.home / relative), rw)
        self.assertFalse(any(path.startswith(str(self.home / ".copilot")) for path in rw))
        self.assertNotIn(str(self.home / "missing"), rw)
        self.assertIn("/Volumes/offline", rw)
        self.assertIn("missing", output)
        self.assertIn(".copilot", output)

    def test_policy_validation_user_denies_and_boolean_preservation(self) -> None:
        (self.home / ".config/git").mkdir(parents=True)
        self.set_policy({
            "readwritePaths": ["relative", "/bad\npath", str(self.home), "/Users"],
            "readonlyPaths": ["relative"],
            "deniedPaths": ["relative", str(self.home / ".config"), str(self.home / "code")],
            "allowGitCredentials": True, "allowGhCredentials": False,
            "allowOutbound": False, "allowLocalNetwork": False,
        })
        code, output = self.run_cli("apply", "--confirm", self.digest())
        self.assertEqual(0, code, output)
        policy = self.policies()[0]
        for field in self.app.PATH_FIELDS:
            self.assertNotIn("relative", policy[field])
            self.assertNotIn("/bad\npath", policy[field])
        self.assertNotIn(str(self.home / ".config/git"), policy["readonlyPaths"])
        self.assertNotIn(str(self.home / ".config"), policy["readwritePaths"])
        self.assertNotIn(str(self.home / "code"), policy["readwritePaths"])
        self.assertTrue(policy["allowGitCredentials"])
        self.assertFalse(policy["allowGhCredentials"])
        self.assertIn("example: removed invalid", output)
        self.assertIn("broad existing", output)
        self.assertIn("overrides existing false", output)
        for flag, expected in (("--no-mask-credentials", False), ("--mask-credentials", True)):
            code, output = self.run_cli("apply", flag, "--confirm", self.digest(flag))
            self.assertEqual(0, code, output)
            self.assertEqual(expected, self.policies()[0]["allowGitCredentials"])
            self.assertEqual(expected, self.policies()[0]["allowGhCredentials"])
            self.assertIn("credential value overridden", output)

    def test_old_sibling_backups_are_warned_about(self) -> None:
        old = self.db.parent / "data.db.before-sandbox-setup-fixture"
        old.touch()
        code, output = self.run_cli("plan")
        self.assertEqual(0, code, output)
        self.assertIn(str(old), output)
        self.assertIn("not covered by the deny list", output)
        self.assertIn("deleting", output)

    def test_guide_includes_machine_paths_and_handles_unavailable_db(self) -> None:
        (self.home / ".gradle").mkdir()
        before = self.db.read_bytes()
        code, output = self.run_cli("guide")
        self.assertEqual(0, code, output)
        self.assertIn("Settings → Projects", output)
        self.assertIn("example", output)
        self.assertIn(str(self.home / "code"), output)
        self.assertIn(str(self.home / ".gradle"), output)
        self.assertIn(str(self.home / ".ssh"), output)
        self.assertIn("/restart-session", output)
        self.assertEqual(before, self.db.read_bytes())
        self.db.unlink()
        code, output = self.run_cli("guide", "--mask-credentials")
        self.assertEqual(2, code, output)
        self.assertIn("add your code folders", output)
        self.assertIn("loopback deny", output)

    def test_guide_uses_current_ui_labels_and_explains_session_toggle_precedence(self) -> None:
        code, output = self.run_cli("guide")
        self.assertEqual(0, code, output)
        for label in ("Sandbox new sessions", "Additional read/write", "Additional read-only",
                      "Denied", "Outbound internet", "Local network", "Git credentials",
                      "GitHub CLI credentials", "/sandbox on"):
            self.assertIn(label, output)
        self.assertNotIn("allowGitCredentials=none", output)

    def test_json_plan_is_parseable_and_does_not_disclose_unknown_values(self) -> None:
        self.set_policy({"extra": {"fixture": "do-not-echo"}})
        before = self.db.read_bytes()
        code, output = self.run_cli("plan", "--json")
        self.assertEqual(0, code, output)
        result = json.loads(output)
        self.assertRegex(result["digest"], r"^[0-9a-f]{64}$")
        self.assertTrue(result["changed"])
        self.assertEqual("example", result["projects"][0]["name"])
        self.assertIn("readwritePaths", result["projects"][0]["diff"])
        self.assertNotIn("do-not-echo", output)
        self.assertEqual(before, self.db.read_bytes())

    def test_backup_includes_committed_wal_contents(self) -> None:
        connection = sqlite3.connect(str(self.db))
        self.addCleanup(connection.close)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("UPDATE projects SET name = ?", ("wal-example",))
        connection.commit()
        code, output = self.run_cli("apply", "--confirm", self.digest())
        self.assertEqual(0, code, output)
        backup = next((self.db.parent / "app-sandbox-setup-backups").iterdir())
        with sqlite3.connect(str(backup)) as copied:
            self.assertEqual("ok", copied.execute("PRAGMA integrity_check").fetchone()[0])
            self.assertEqual(("wal-example", 0), copied.execute(
                "SELECT name, sandbox_enabled FROM projects"
            ).fetchone())
            self.assertEqual(0, copied.execute("SELECT count(*) FROM project_sandbox_policies").fetchone()[0])

    def test_backup_failure_and_symlink_abort_without_writes(self) -> None:
        digest = self.digest()
        before = self.db.read_bytes()
        with mock.patch.object(self.app, "backup_db", side_effect=OSError("private fixture")):
            code, output = self.run_cli("apply", "--confirm", digest)
        self.assertEqual(1, code, output)
        self.assertNotIn("private fixture", output)
        self.assertEqual(before, self.db.read_bytes())
        target = self.root / "external-backups"
        target.mkdir()
        (self.db.parent / "app-sandbox-setup-backups").symlink_to(target, target_is_directory=True)
        code, output = self.run_cli("apply", "--confirm", digest)
        self.assertEqual(1, code, output)
        self.assertEqual(before, self.db.read_bytes())
        self.assertEqual([], list(target.iterdir()))

    def test_write_failure_rolls_back_the_entire_transaction(self) -> None:
        digest = self.digest()
        before = self.db.read_bytes()
        original_open = self.app.open_db

        class FailingWriter:
            def __init__(self, connection):
                self.connection = connection

            def execute(self, query, *parameters):
                if query.startswith("INSERT INTO project_sandbox_policies"):
                    raise sqlite3.OperationalError("private-fixture-error")
                return self.connection.execute(query, *parameters)

            def close(self):
                self.connection.close()

        def open_with_write_failure(path, writable=False):
            connection = original_open(path, writable)
            return FailingWriter(connection) if writable else connection

        with mock.patch.object(self.app, "open_db", side_effect=open_with_write_failure):
            code, output = self.run_cli("apply", "--confirm", digest)
        self.assertEqual(1, code, output)
        self.assertNotIn("private-fixture-error", output)
        self.assertEqual(before, self.db.read_bytes())
        self.assertEqual([], self.policies())
        self.assertEqual(0, len(list((self.db.parent / "app-sandbox-setup-backups").iterdir())))

    def test_extra_required_policy_column_is_rejected_before_backup(self) -> None:
        with sqlite3.connect(str(self.db)) as connection:
            connection.execute("ALTER TABLE project_sandbox_policies ADD COLUMN required TEXT NOT NULL")
        code, output = self.run_cli("apply", "--confirm", "0" * 64)
        self.assertEqual(3, code, output)
        self.assertFalse((self.db.parent / "app-sandbox-setup-backups").exists())

    def test_git_discovery_uses_fixture_config_and_warns_without_leaking_values(self) -> None:
        config_dir = self.home / "git-config"
        config_dir.mkdir()
        for name in ("included", "conditional", "excludes", "template", "hooks"):
            (config_dir / name).touch()
        (config_dir / "included").write_text(
            "[core]\n hooksPath = ~/git-config/hooks\n excludesFile = ~/git-config/excludes\n", encoding="utf-8")
        (self.home / ".gitconfig").write_text(
            '[include]\n path = git-config/included\n'
            '[includeIf "gitdir:never/"]\n path = git-config/conditional\n'
            '[commit]\n template = ~/git-config/template\n gpgsign = true\n'
            '[url "https://fixture.invalid/"]\n insteadOf = fixture-private-value\n',
            encoding="utf-8")
        env = {key: value for key, value in os.environ.items()
               if not key.startswith("GIT_CONFIG") and key != "XDG_CONFIG_HOME"}
        env.update(HOME=str(self.home), GIT_CONFIG_NOSYSTEM="1")
        repo = self.home / "code/repository"
        subprocess.run(["git", "init", "-q", str(repo)], env=env, check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo), "config", "remote.origin.url",
                        "git@fixture.invalid:team/repo"], env=env, check=True, capture_output=True)
        with mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": "/nonexistent/host-config",
                                         "XDG_CONFIG_HOME": "/nonexistent/host-xdg"}):
            code, output = self.run_cli("apply", "--confirm", self.digest())
        self.assertEqual(0, code, output)
        readonly = self.policies()[0]["readonlyPaths"]
        self.assertIn(str(self.home / ".gitconfig"), readonly)
        for name in ("included", "conditional", "excludes", "template", "hooks"):
            self.assertIn(str(config_dir / name), readonly)
        self.assertIn("commit.gpgsign", output)
        self.assertIn("example: SSH remote", output)
        self.assertNotIn("git@fixture.invalid", output)
        self.assertNotIn("fixture-private-value", output)

    def test_disk_credentials_are_readonly_with_private_value_free_warnings(self) -> None:
        hosts = self.home / ".config/gh/hosts.yml"
        hosts.parent.mkdir(parents=True)
        hosts.write_text("fixture.invalid:\n  oauth_token: fixture-private-value\n", encoding="utf-8")
        docker = self.home / ".docker/config.json"
        docker.parent.mkdir()
        docker.write_text('{"auths":{"fixture.invalid":{"auth":"fixture-private-value"}}}', encoding="utf-8")
        code, output = self.run_cli("apply", "--confirm", self.digest())
        self.assertEqual(0, code, output)
        policy = self.policies()[0]
        for path in (hosts, docker):
            self.assertIn(str(path), policy["readonlyPaths"])
            self.assertNotIn(str(path), policy["deniedPaths"])
        for relative in (".config/github-copilot", ".config/configstore", ".config/op", ".azure"):
            self.assertIn(str(self.home / relative), policy["deniedPaths"])
        self.assertIn("inline token", output)
        self.assertIn("inline auth", output)
        self.assertNotIn("fixture-private-value", output)

    def test_empty_db_and_unicode_output_keep_canonical_digest(self) -> None:
        with sqlite3.connect(str(self.db)) as connection:
            connection.execute("UPDATE projects SET name = 'æøå'")
        code, output = self.run_cli("plan", "--json")
        self.assertEqual(0, code, output)
        self.assertIn("æøå", output)
        self.assertNotIn("\\u00", output)
        self.assertEqual('"\\u00e6\\u00f8\\u00e5"', self.app.canonical("æøå"))
        with sqlite3.connect(str(self.db)) as connection:
            connection.execute("DELETE FROM projects")
        for command in ("plan", "guide"):
            code, output = self.run_cli(command)
            self.assertEqual(1, code, output)
            self.assertIn("add a project in the app first", output)

    def test_rollback_preview_confirm_restores_only_shared_project_settings(self) -> None:
        code, output = self.run_cli("apply", "--confirm", self.digest())
        self.assertEqual(0, code, output)
        directory = self.db.parent / "app-sandbox-setup-backups"
        original = next(directory.iterdir())
        with sqlite3.connect(str(self.db)) as connection:
            connection.execute("UPDATE projects SET name = 'renamed'")
            connection.execute("INSERT INTO projects(id, name, main_repo_path, sandbox_enabled) VALUES ('new', 'new project', '/Volumes/new/repo', 1)")
            connection.execute("INSERT INTO project_sandbox_policies VALUES ('new', '{\"custom\":true}')")
        before = self.db.read_bytes()
        code, output = self.run_cli("rollback", "--from", str(original))
        self.assertEqual(0, code, output)
        self.assertIn("sandbox_enabled: 1 -> 0", output)
        self.assertIn("new project", output)
        self.assertIn("missing from backup", output)
        self.assertEqual(before, self.db.read_bytes())
        digest = re.search(r"Plan digest: ([0-9a-f]{64})", output).group(1)
        code, output = self.run_cli("rollback", "--from", str(original), "--confirm", "0" * 64)
        self.assertEqual(4, code, output)
        self.assertEqual(1, len(list(directory.iterdir())))
        code, output = self.run_cli("rollback", "--from", str(original), "--confirm", digest)
        self.assertEqual(0, code, output)
        self.assertEqual(2, len(list(directory.iterdir())))
        with sqlite3.connect(str(self.db)) as connection:
            self.assertEqual([("new", 1, "new project"), ("p1", 0, "renamed")],
                             connection.execute("SELECT id, sandbox_enabled, name FROM projects ORDER BY id").fetchall())
            self.assertEqual([("new", '{"custom":true}')], connection.execute(
                "SELECT * FROM project_sandbox_policies ORDER BY project_id").fetchall())

    def test_verify_behavioral_gate_and_presence_only_environment_reporting(self) -> None:
        probes = {"HOME write": "denied", "DB open": "denied", "loopback": "OK",
                  "cache write": "OK", "readonly write": "denied"}
        with mock.patch.object(self.app, "behavioral_probes", return_value=probes, create=True), \
                mock.patch.object(self.app, "open_db", side_effect=AssertionError("verify must not access store")), \
                mock.patch.dict(os.environ, {"GH_TOKEN": "fixture-private-value",
                                             "HTTPS_PROXY": "http://fixture-private-value@127.0.0.1:4321"}):
            code, output = self.run_cli("verify")
            self.assertEqual(0, code, output)
            self.assertIn("expected", output)
            self.assertIn("actual", output)
            self.assertIn("GH_TOKEN set: yes", output)
            self.assertIn("proxy env points to 127.0.0.1: yes", output)
            self.assertNotIn("fixture-private-value", output)
            probes["loopback"] = "denied"
            code, output = self.run_cli("verify", "--mask-credentials")
            self.assertEqual(0, code, output)
            probes["HOME write"] = "OK"
            code, output = self.run_cli("verify", "--mask-credentials")
            self.assertEqual(7, code, output)
            self.assertIn("this session is not sandboxed", output)
            self.assertIn("enterprise managed settings", output)

    def test_no_docker_omits_readonly_docker_additions_too(self) -> None:
        (self.home / ".docker/cli-plugins").mkdir(parents=True)
        (self.home / ".docker/config.json").write_text("{}", encoding="utf-8")
        code, output = self.run_cli("apply", "--no-docker", "--confirm", self.digest("--no-docker"))
        self.assertEqual(0, code, output)
        for field in ("readwritePaths", "readonlyPaths"):
            self.assertFalse(any(path.startswith(str(self.home / ".docker"))
                                 for path in self.policies()[0][field]))

    def test_casefold_home_parent_is_not_granted(self) -> None:
        raw = str(self.home).replace("/home", "/HoMe") + "/repo"
        with sqlite3.connect(str(self.db)) as connection:
            connection.execute("UPDATE projects SET main_repo_path = ?", (raw,))
        original_exists = Path.exists
        with mock.patch.object(Path, "exists", lambda path: True if str(path).casefold() == raw.casefold()
                               else original_exists(path)):
            code, output = self.run_cli("plan", "--json")
        self.assertEqual(0, code, output)
        rw = json.loads(output)["projects"][0]["diff"]["readwritePaths"]["added"]
        self.assertFalse(any(path.casefold() == str(self.home).casefold() for path in rw))
        self.assertTrue(any(path.casefold() == raw.casefold() for path in rw))
        self.assertIn("unsafe code root", output)
        alias = self.root / "alias-home"
        alias.symlink_to(self.home, target_is_directory=True)
        self.assertTrue(self.app.same_path(alias, self.home))

    def test_stock_git_is_not_launched_without_command_line_tools(self) -> None:
        result = subprocess.CompletedProcess([], 1, stdout="", stderr="")
        with mock.patch.object(self.app.shutil, "which", return_value="/usr/bin/git"), \
                mock.patch.object(self.app.sys, "platform", "darwin"), \
                mock.patch.object(self.app.subprocess, "run", return_value=result) as run:
            code, output = self.run_cli("plan")
        self.assertEqual(0, code, output)
        self.assertIn("install dialog", output)
        self.assertEqual(["/usr/bin/xcode-select", "-p"], run.call_args[0][0])
        self.assertEqual(1, run.call_count)

    def test_optional_docker_context_discovery_is_bounded_and_home_scoped(self) -> None:
        parent = self.home / "custom-docker"
        parent.mkdir()
        result = subprocess.CompletedProcess([], 0, stdout="unix://" + str(parent / "docker.sock") + "\n")
        with mock.patch.dict(os.environ, {"DOCKER_HOST": ""}), \
                mock.patch.object(self.app.subprocess, "run", return_value=result) as run:
            self.assertEqual(str(parent), self.app.docker_parent(self.home))
            self.assertEqual(["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
                             run.call_args[0][0])
            self.assertEqual(str(self.home), run.call_args[1]["env"]["HOME"])
            self.assertLessEqual(run.call_args[1]["timeout"], 3)
            result.stdout = "unix:///outside/docker.sock"
            self.assertIsNone(self.app.docker_parent(self.home))

    def test_successful_apply_prunes_only_our_newest_ten_backups(self) -> None:
        directory = self.db.parent / "app-sandbox-setup-backups"
        directory.mkdir()
        for index in range(12):
            (directory / f"data.db.20000101T0000{index:02d}.000000Z").touch()
        unrelated = directory / "keep-me"
        unrelated.touch()
        link = directory / "data.db.19990101T000000.000000Z"
        link.symlink_to(unrelated)
        code, output = self.run_cli("apply", "--confirm", self.digest())
        self.assertEqual(0, code, output)
        ours = [path for path in directory.iterdir() if path.name.startswith("data.db.") and not path.is_symlink()]
        self.assertEqual(10, len(ours))
        self.assertTrue(unrelated.exists())
        self.assertTrue(link.is_symlink())
        self.assertFalse((directory / "data.db.20000101T000000.000000Z").exists())

    def test_real_verify_probes_only_open_db_and_clean_temp_files(self) -> None:
        (self.home / ".gradle").mkdir()
        (self.home / ".config/git").mkdir(parents=True)
        before = set(self.home.rglob("*")), self.db.read_bytes()
        self.assertEqual("OK", self.app.probe_db_open(self.db))
        self.assertEqual("OK", self.app.probe_write(self.home))
        self.assertEqual("OK", self.app.probe_loopback())
        self.assertEqual(before, (set(self.home.rglob("*")), self.db.read_bytes()))
        with mock.patch.object(self.app.os, "write", side_effect=OSError(errno.EACCES, "fixture")):
            self.assertEqual("denied", self.app.probe_write(self.home))
        self.assertEqual(before, (set(self.home.rglob("*")), self.db.read_bytes()))

    def test_copilot_symlink_is_not_a_code_root(self) -> None:
        target = self.root / "escaped/repo"
        target.mkdir(parents=True)
        (self.db.parent / "escape").symlink_to(target, target_is_directory=True)
        with sqlite3.connect(str(self.db)) as connection:
            connection.execute("INSERT INTO worktrees VALUES ('escape', 'p1', ?, 'branch')",
                               (str(self.db.parent / "escape"),))
        code, output = self.run_cli("plan", "--json")
        self.assertEqual(0, code, output)
        rw = json.loads(output)["projects"][0]["diff"]["readwritePaths"]["added"]
        self.assertNotIn(str(target), rw)
        self.assertNotIn(str(target.parent), rw)
        self.assertIn("never a code root", output)

    def test_narrow_plugin_readonly_grant_is_not_reported_as_broad(self) -> None:
        self.set_policy({"readonlyPaths": [str(self.home / ".copilot/installed-plugins")]})
        code, output = self.run_cli("plan")
        self.assertEqual(0, code, output)
        self.assertNotIn("broad existing", output)

    def test_invalid_code_path_is_skipped_before_git_discovery(self) -> None:
        with sqlite3.connect(str(self.db)) as connection:
            connection.execute("UPDATE projects SET main_repo_path = NULL")
        code, output = self.run_cli("plan")
        self.assertEqual(0, code, output)
        self.assertIn("Code path skipped", output)

    def test_backup_target_open_failure_closes_source_and_leaves_no_orphan(self) -> None:
        digest = self.digest()
        before = self.db.read_bytes()
        original_open, original_connect = self.app.open_db, self.app.sqlite3.connect
        sources = []

        def recording_open(path, writable=False):
            connection = original_open(path, writable)
            if writable:
                return connection
            wrapper = mock.Mock(wraps=connection)
            sources.append(wrapper)
            self.addCleanup(connection.close)
            return wrapper

        def failing_target(path, *args, **kwargs):
            if "app-sandbox-setup-backups/data.db." in str(path):
                raise sqlite3.OperationalError("fixture-private-value")
            return original_connect(path, *args, **kwargs)

        with mock.patch.object(self.app, "open_db", side_effect=recording_open), \
                mock.patch.object(self.app.sqlite3, "connect", side_effect=failing_target):
            code, output = self.run_cli("apply", "--confirm", digest)
        self.assertEqual(1, code, output)
        self.assertNotIn("fixture-private-value", output)
        self.assertEqual(before, self.db.read_bytes())
        self.assertEqual([], list((self.db.parent / "app-sandbox-setup-backups").iterdir()))
        self.assertEqual(1, len(sources))
        sources[0].close.assert_called_once()

    def test_empty_inline_credentials_do_not_warn(self) -> None:
        hosts = self.home / ".config/gh/hosts.yml"
        hosts.parent.mkdir(parents=True)
        hosts.write_text("fixture.invalid:\n  oauth_token:\n  user: fixture\n", encoding="utf-8")
        config = self.home / ".docker/config.json"
        config.parent.mkdir()
        config.write_text('{"auths":{"fixture.invalid":{"auth":""}}}', encoding="utf-8")
        code, output = self.run_cli("plan")
        self.assertEqual(0, code, output)
        self.assertNotIn("contains an inline token", output)
        self.assertNotIn("contains inline auth", output)

    def test_main_repo_unsafe_parent_and_denied_ancestor_fall_back(self) -> None:
        for relative in ("Downloads/repo", "Documents/repo", "Desktop/repo",
                         "Library/Mobile Documents/repo", ".config/repo"):
            with self.subTest(relative=relative):
                specific = self.home / relative
                specific.mkdir(parents=True, exist_ok=True)
                with sqlite3.connect(str(self.db)) as connection:
                    connection.execute("UPDATE projects SET main_repo_path = ?", (str(specific),))
                code, output = self.run_cli("plan", "--json")
                self.assertEqual(0, code, output)
                rw = json.loads(output)["projects"][0]["diff"]["readwritePaths"]["added"]
                self.assertIn(str(specific), rw)
                self.assertIn("unsafe code root", output)

    def test_system_paths_stay_blocked_with_production_guards(self) -> None:
        self.app.SYSTEM_AREAS = (
            "/System", "/Library", "/usr", "/bin", "/sbin", "/etc", "/var",
            "/private", "/opt", "/Applications",
        )
        with sqlite3.connect(str(self.db)) as connection:
            connection.execute("DELETE FROM projects")
            for index, path in enumerate((
                "/", "/Users", "/Volumes", "/usr/local/project", "/opt/project",
                "/private/var/project", "/Library/project", "/System/project",
            )):
                connection.execute("INSERT INTO projects(id, name, main_repo_path) VALUES (?, ?, ?)",
                                   (str(index), "fixture", path))
        code, output = self.run_cli("apply", "--confirm", self.digest())
        self.assertEqual(0, code, output)
        for policy in self.policies():
            # Fixed tool exceptions /tmp and /private/tmp are intentionally allowed.
            self.assertEqual([path for path in ("/tmp", "/private/tmp") if Path(path).exists()],
                             policy["readwritePaths"])

    def test_usage_errors_return_1(self) -> None:
        for command, options in (("apply", ()), ("unknown", ()), ("plan", ("--unknown",))):
            code, output = self.run_cli(command, *options)
            self.assertEqual(1, code, output)

    def test_backup_permissions_do_not_depend_on_umask(self) -> None:
        digest = self.digest()
        previous = os.umask(0o777)
        try:
            code, output = self.run_cli("apply", "--confirm", digest)
        finally:
            os.umask(previous)
        self.assertEqual(0, code, output)
        backup = next((self.db.parent / "app-sandbox-setup-backups").iterdir())
        self.assertEqual(0o600, backup.stat().st_mode & 0o777)

    def test_apply_all_projects_backs_up_and_is_idempotent(self) -> None:
        with sqlite3.connect(str(self.db)) as connection:
            connection.execute(
                "INSERT INTO projects(id, name, main_repo_path) VALUES (?, ?, ?)",
                ("p2", "second", str(self.root / "other/repository")),
            )
        code, output = self.run_cli("apply", "--confirm", self.digest())
        self.assertEqual(0, code, output)
        with sqlite3.connect(str(self.db)) as connection:
            self.assertEqual([(1,), (1,)], connection.execute("SELECT sandbox_enabled FROM projects").fetchall())
        self.assertEqual(2, len(self.policies()))
        backups = self.db.parent / "app-sandbox-setup-backups"
        self.assertEqual(0o700, backups.stat().st_mode & 0o777)
        files = list(backups.iterdir())
        self.assertEqual(1, len(files))
        self.assertEqual(0o600, files[0].stat().st_mode & 0o777)
        with sqlite3.connect(str(files[0])) as connection:
            self.assertEqual("ok", connection.execute("PRAGMA integrity_check").fetchone()[0])
            self.assertEqual([(0,), (0,)], connection.execute("SELECT sandbox_enabled FROM projects").fetchall())
        code, output = self.run_cli("plan")
        self.assertEqual(0, code, output)
        self.assertIn("no changes", output)
        before = self.db.read_bytes(), self.db.stat().st_mtime_ns
        code, output = self.run_cli("apply", "--confirm", self.digest())
        self.assertEqual(0, code, output)
        self.assertIn("no changes", output)
        self.assertEqual(before, (self.db.read_bytes(), self.db.stat().st_mtime_ns))
        self.assertEqual(files, list(backups.iterdir()))


if __name__ == "__main__":
    unittest.main()
