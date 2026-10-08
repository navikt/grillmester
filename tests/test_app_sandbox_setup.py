from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import re
import sqlite3
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
        self.db = self.home / ".copilot/data.db"
        self.db.parent.mkdir()
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
        spec.loader.exec_module(self.app)
        # macOS TMPDIR lives below /private/var, unlike real developer homes.
        # Keep temporary fixtures there while retaining all other system guards.
        if hasattr(self.app, "SYSTEM_AREAS"):
            self.app.SYSTEM_AREAS = tuple(
                path for path in self.app.SYSTEM_AREAS if path not in ("/private", "/var")
            )

    def run_cli(self, command: str, *options: str) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = self.app.main([
                command, "--db", str(self.db), "--home", str(self.home), *options,
            ])
        return code, output.getvalue()

    def test_plan_is_read_only_and_prints_diff_and_digest(self) -> None:
        before = self.db.read_bytes(), self.db.stat().st_mtime_ns
        code, output = self.run_cli("plan")
        self.assertEqual(0, code, output)
        self.assertIn("example", output)
        self.assertIn(f'+ readwritePaths: "{self.home / "code"}"', output)
        self.assertIn("sandbox_enabled: 0 -> 1", output)
        self.assertRegex(output, r"Plan digest: [0-9a-f]{64}")
        self.assertEqual(before, (self.db.read_bytes(), self.db.stat().st_mtime_ns))
        self.assertEqual(["data.db"], [p.name for p in self.db.parent.iterdir()])

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
                    code, output = self.run_cli(command, *(("--confirm", "0" * 64) if command == "apply" else ()))
                    self.assertEqual(3, code, output)
                    self.assertIn("guide", output)
                    self.assertEqual(before, self.db.read_bytes())
        with sqlite3.connect(str(self.db)) as connection:
            connection.execute("UPDATE project_sandbox_policies SET policy_json = ?", ("{private invalid",))
        code, output = self.run_cli("plan")
        self.assertEqual(3, code, output)
        self.assertNotIn("private invalid", output)

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
        self.assertIn("sandbox is probably ON", output)
        self.assertIn("app was never started", output)
        self.assertFalse(self.db.exists())
        self.db.mkdir()
        code, output = self.run_cli("plan")
        self.assertEqual(2, code, output)
        with mock.patch.object(self.app.sqlite3, "connect", side_effect=PermissionError("private fixture")):
            code, output = self.run_cli("apply", "--confirm", "0" * 64)
        self.assertEqual(2, code, output)
        self.assertNotIn("private fixture", output)

    def test_mask_credentials_sets_both_flags_and_warns_about_loopback(self) -> None:
        code, output = self.run_cli("apply", "--mask-credentials", "--confirm", self.digest("--mask-credentials"))
        self.assertEqual(0, code, output)
        policy = self.policies()[0]
        self.assertTrue(policy["allowGitCredentials"])
        self.assertTrue(policy["allowGhCredentials"])
        self.assertTrue(policy["allowLocalNetwork"])
        self.assertIn("loopback deny", output)

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
        self.assertEqual(0, code, output)
        self.assertIn("add your code folders", output)
        self.assertIn("loopback deny", output)

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
        self.assertEqual(1, len(list((self.db.parent / "app-sandbox-setup-backups").iterdir())))

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
