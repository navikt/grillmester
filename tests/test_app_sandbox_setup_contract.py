"""Non-output-pinning scenarios ported from the removed differential oracle."""

import json
import os
import sqlite3
import unittest
from unittest import mock

import test_app_sandbox_setup as fixtures


class ContractTest(unittest.TestCase):
    setUp = fixtures.AppSandboxSetupTest.setUp
    run_cli = fixtures.AppSandboxSetupTest.run_cli
    digest = fixtures.AppSandboxSetupTest.digest
    set_policy = fixtures.AppSandboxSetupTest.set_policy
    policies = fixtures.AppSandboxSetupTest.policies

    def test_unstatable_policy_paths_do_not_abort_plan(self):
        blocked = self.home / "blocked"
        blocked.mkdir()
        child = blocked / "child"
        child.touch()
        paths = [self.home / ("x" * 300),
                 self.home / "/".join(["x" * 100] * (os.pathconf(str(self.home), "PC_PATH_MAX") // 100 + 2))]
        for path in paths:
            with self.subTest(path_length=len(str(path))):
                self.set_policy({"readwritePaths": [str(path)]})
                code, output = self.run_cli("plan", "--json")
                self.assertEqual(0, code, output)
                self.assertTrue(json.loads(output)["changed"])
        if os.geteuid() != 0:
            self.set_policy({"readwritePaths": [str(child)]})
            blocked.chmod(0)
            try:
                code, output = self.run_cli("plan", "--json")
                self.assertEqual(0, code, output)
            finally:
                blocked.chmod(0o700)

    def test_tools_masking_and_docker_combination_matrix_is_idempotent(self):
        for relative in (".gradle", ".m2", ".config/git", ".docker", ".rd",
                         "Library/Caches/copilot/pkg", "Library/Caches/copilot/mcp"):
            (self.home / relative).mkdir(parents=True, exist_ok=True)
        for flags, mask in (((), False), (("--mask-credentials",), True),
                            (("--no-mask-credentials",), False), (("--no-docker",), False),
                            (("--mask-credentials", "--no-docker"), True),
                            (("--no-mask-credentials", "--no-docker"), False)):
            with self.subTest(flags=flags):
                with sqlite3.connect(str(self.db)) as db:
                    db.execute("DELETE FROM project_sandbox_policies")
                    db.execute("UPDATE projects SET sandbox_enabled = 0")
                code, output = self.run_cli("apply", *flags, "--confirm", self.digest(*flags))
                self.assertEqual(0, code, output)
                policy = self.policies()[0]
                self.assertEqual(mask, policy["allowGitCredentials"])
                self.assertEqual(mask, policy["allowGhCredentials"])
                self.assertEqual("--no-docker" not in flags, str(self.home / ".docker") in policy["readwritePaths"])
                code, output = self.run_cli("plan", *flags)
                self.assertEqual(0, code, output)
                self.assertIn("no changes", output)

    def test_missing_git_and_exit_codes_across_commands(self):
        from app_sandbox import discovery
        original = discovery.shutil.which
        with mock.patch.object(discovery.shutil, "which",
                               side_effect=lambda tool, **kw: None if tool == "git" else original(tool, **kw)):
            code, output = self.run_cli("plan")
        self.assertEqual(0, code, output)
        self.assertIn("git is unavailable", output)
        for failure, expected in (("no-projects", 1), ("schema", 3), ("missing-db", 2)):
            with self.subTest(failure=failure):
                if failure == "missing-db":
                    self.db.unlink()
                else:
                    with sqlite3.connect(str(self.db)) as db:
                        db.execute("DELETE FROM projects" if failure == "no-projects" else "DROP TABLE worktrees")
                for command, flags in (("plan", ()), ("plan", ("--json",)), ("guide", ()),
                                       ("apply", ("--confirm", "wrong"))):
                    code, output = self.run_cli(command, *flags)
                    self.assertEqual(expected, code, output)

    def test_rollback_unknown_policy_keys_are_names_only_and_formatting_is_explicit(self):
        self.set_policy({"unknownA": "fixture-private-value", "unknownB": 1})
        code, output = self.run_cli("apply", "--confirm", self.digest())
        self.assertEqual(0, code, output)
        backup = self.root / "snapshot.db"
        with sqlite3.connect(str(self.db)) as source, sqlite3.connect(str(backup)) as target:
            source.backup(target)
        with sqlite3.connect(str(self.db)) as db:
            raw = db.execute("SELECT policy_json FROM project_sandbox_policies").fetchone()[0]
            data = json.loads(raw)
            data["unknownA"] = "different-private-value"
            db.execute("UPDATE project_sandbox_policies SET policy_json = ?", (json.dumps(data),))
        code, output = self.run_cli("rollback", "--from", str(backup))
        self.assertEqual(0, code, output)
        self.assertIn('policy JSON rewritten: "unknownA"', output)
        self.assertNotIn("unknownB", output)
        self.assertNotIn("private-value", output)
        with sqlite3.connect(str(self.db)) as db:
            db.execute("UPDATE project_sandbox_policies SET policy_json = ?", (json.dumps(json.loads(raw), indent=2),))
        code, output = self.run_cli("rollback", "--from", str(backup))
        self.assertEqual(0, code, output)
        self.assertIn("policy JSON rewritten: formatting only", output)

    def test_move_failures_and_late_collisions_keep_commit_and_both_files(self):
        from app_sandbox import backups
        source = self.db.parent / "data.db.fixture"
        source.write_bytes(b"fixture")
        digest = self.digest("--move-backups")
        with mock.patch.object(backups.os, "rename", side_effect=OSError("fixture-private-value")):
            code, output = self.run_cli("apply", "--move-backups", "--confirm", digest)
        self.assertEqual(0, code, output)
        self.assertTrue(self.policies())
        self.assertTrue(source.exists())
        self.assertIn("backup move failed", output)
        self.assertNotIn("fixture-private-value", output)
        original_write = self.app.write_changes
        destination = self.db.parent / "app-sandbox-setup-backups" / source.name

        def collide_after_commit(*args):
            result = original_write(*args)
            destination.write_bytes(b"late fixture")
            return result

        with mock.patch.object(self.app, "write_changes", side_effect=collide_after_commit):
            code, output = self.run_cli("apply", "--move-backups", "--confirm", self.digest("--move-backups"))
        self.assertEqual(0, code, output)
        self.assertEqual(b"fixture", source.read_bytes())
        self.assertEqual(b"late fixture", destination.read_bytes())
        self.assertIn("backup move failed", output)

    def test_timestamp_named_moved_copies_never_enter_retention_namespace(self):
        source = self.db.parent / "data.db.20260101T000000.000000Z"
        source.write_bytes(b"user fixture backup")
        code, output = self.run_cli("apply", "--move-backups", "--confirm", self.digest("--move-backups"))
        self.assertEqual(0, code, output)
        destination = self.db.parent / "app-sandbox-setup-backups" / (source.name + ".1")
        self.assertEqual(b"user fixture backup", destination.read_bytes())
        self.app.prune_backups(self.home)
        self.assertEqual(b"user fixture backup", destination.read_bytes())

    def test_unrecognized_existing_managed_content_is_not_echoed(self):
        from app_sandbox import instructions
        text = instructions.BEGIN + "\nfixture-private-value\n" + instructions.END
        with sqlite3.connect(str(self.db)) as db:
            db.execute("UPDATE projects SET instructions = ?", ("user\n" + text + "\nafter",))
        for flags in ((), ("--json",)):
            code, output = self.run_cli("plan", *flags)
            self.assertEqual(0, code, output)
            self.assertNotIn("fixture-private-value", output)
            self.assertIn("contents not displayed", output)


if __name__ == "__main__":
    unittest.main()
