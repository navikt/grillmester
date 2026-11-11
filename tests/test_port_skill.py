from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


PORT = load("grillmester_port_skill", "port_skill.py")
VALIDATE = load("grillmester_validate_for_port_skill", "validate.py")
PLACEHOLDER = "0" * 64
OTHER_REVISION = "a" * 40
# The developer's own Git configuration and hooks stay out of the fixtures.
GIT_ENVIRONMENT = {
    "PATH": os.environ["PATH"],
    "GIT_AUTHOR_NAME": "Fixture",
    "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
    "GIT_COMMITTER_NAME": "Fixture",
    "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}


def git(repo: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *arguments],
        check=True,
        capture_output=True,
        text=True,
        env=GIT_ENVIRONMENT,
    ).stdout.strip()


class PortSkillTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.source = base / "source"
        self.root = base / "root"
        self.skill = self.root / "plugin/skills/demo"
        # The remote's address ends in the repository the lock names.
        self.remote = base / "remotes/navikt/owner.git"
        self.remote.mkdir(parents=True)
        git(self.remote, "init", "-q", "--bare", "--initial-branch=main")

        (self.source / "skills/demo/references").mkdir(parents=True)
        git(self.source, "init", "-q", "--initial-branch=main")
        git(self.source, "remote", "add", "origin", str(self.remote))
        self.write_source("SKILL.md", "---\nname: demo\n---\n# Demo\n")
        self.write_source("references/a.md", "# A\n")
        self.write_source("references/old.md", "# Old\n")
        self.write_source("README.md", "Catalog text that is not shipped.\n")
        self.write_source("metadata.json", "{}\n")
        self.first = self.publish("first")

        for directory in ("policy", "plugin/skills"):
            (self.root / directory).mkdir(parents=True)
        for record in PORT.REVISION_RECORDS:
            (self.root / record).write_text(f"Ported at `{self.first}`.\n")
        self.write_lock(
            {
                "sources": {
                    "owner": {"repository": "navikt/owner", "revision": self.first},
                    "other": {"repository": "navikt/other", "revision": OTHER_REVISION},
                },
                "agents": {},
                "skills": {
                    "demo": {
                        "source": "owner",
                        "sourcePath": "skills/demo",
                        "disposition": "ported",
                        "contentSha256": PLACEHOLDER,
                    },
                    "local": {"source": "other", "sourcePath": "x", "disposition": "adapted"},
                },
            }
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_source(self, relative: str, text: str) -> None:
        path = self.source / "skills/demo" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def commit(self, message: str) -> str:
        git(self.source, "add", "-A")
        git(self.source, "commit", "-q", "-m", message)
        return git(self.source, "rev-parse", "HEAD")

    def publish(self, message: str) -> str:
        revision = self.commit(message)
        git(self.source, "push", "-q", "origin", "main")
        return revision

    def write_lock(self, lock: dict) -> None:
        (self.root / "policy/content-lock.json").write_text(
            json.dumps(lock, indent=2) + "\n", encoding="utf-8"
        )

    def lock(self) -> dict:
        return json.loads((self.root / "policy/content-lock.json").read_text())

    def snapshot(self) -> dict[Path, bytes]:
        return {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}

    def run_port(self, *arguments: str) -> tuple[int, str]:
        output = io.StringIO()
        with (
            contextlib.redirect_stdout(output),
            contextlib.redirect_stderr(output),
            mock.patch.dict(os.environ, GIT_ENVIRONMENT),
        ):
            code = PORT.main(
                ["demo", "--source", str(self.source), "--root", str(self.root), *arguments]
            )
        return code, output.getvalue()

    def test_port_takes_the_skill_without_catalog_files_and_binds_it(self) -> None:
        code, _ = self.run_port()

        self.assertEqual(0, code)
        self.assertEqual(
            {"SKILL.md", "references/a.md", "references/old.md"},
            set(PORT.local_files(self.skill)),
        )
        self.assertEqual(
            (self.source / "skills/demo/SKILL.md").read_bytes(),
            (self.skill / "SKILL.md").read_bytes(),
        )
        digest = self.lock()["skills"]["demo"]["contentSha256"]
        self.assertNotEqual(PLACEHOLDER, digest)
        # The validator binds a ported skill with the same digest.
        self.assertEqual(digest, VALIDATE.ported_content_digest(self.skill))
        self.assertEqual(0, self.run_port("--check")[0])

    def test_files_beside_the_references_come_along(self) -> None:
        self.write_source("scripts/check.sh", "echo ok\n")
        self.write_source("references/deep/b.md", "# B\n")
        second = self.publish("a script the skill runs")

        self.assertEqual(0, self.run_port("--revision", second)[0])

        self.assertEqual(
            {
                "SKILL.md",
                "references/a.md",
                "references/old.md",
                "references/deep/b.md",
                "scripts/check.sh",
            },
            set(PORT.local_files(self.skill)),
        )

    def test_check_reads_git_objects_not_the_working_tree(self) -> None:
        self.run_port()
        self.write_source("SKILL.md", "uncommitted edit in the checkout\n")

        self.assertEqual(0, self.run_port("--check")[0])

    def test_check_names_every_difference(self) -> None:
        self.run_port()
        (self.skill / "references/a.md").write_text("# Edited here\n")
        (self.skill / "references/local.md").write_text("# Local\n")
        (self.skill / "SKILL.md").unlink()

        code, output = self.run_port("--check")

        self.assertEqual(1, code)
        for line in (
            "changed: references/a.md",
            "not in the source: references/local.md",
            "missing: SKILL.md",
        ):
            self.assertIn(line, output)

    def test_check_rejects_a_digest_that_does_not_match_the_source(self) -> None:
        self.run_port()
        lock = self.lock()
        lock["skills"]["demo"]["contentSha256"] = "1" * 64
        self.write_lock(lock)

        code, output = self.run_port("--check")

        self.assertEqual(1, code)
        self.assertIn("contentSha256 in the content lock does not match", output)

    def test_a_commit_the_named_repository_does_not_have_is_refused(self) -> None:
        self.run_port()
        before = self.snapshot()
        self.write_source("references/a.md", "# Only on this machine\n")
        unpushed = self.commit("local only")

        code, output = self.run_port("--revision", unpushed)

        self.assertEqual(2, code)
        self.assertIn("is not on a branch fetched from navikt/owner", output)
        self.assertEqual(before, self.snapshot())

    def test_a_checkout_of_another_repository_is_refused(self) -> None:
        self.run_port()
        git(self.source, "remote", "set-url", "origin", str(self.remote.parent / "fork.git"))

        for arguments in ((), ("--check",)):
            with self.subTest(arguments=arguments):
                code, output = self.run_port(*arguments)
                self.assertEqual(2, code)
                self.assertIn("has no remote for navikt/owner", output)

    def test_moving_the_revision_updates_files_lock_and_records(self) -> None:
        self.run_port()
        self.write_source("references/a.md", "# A, revised\n")
        self.write_source("references/b.md", "# B\n")
        (self.source / "skills/demo/references/old.md").unlink()
        second = self.publish("second")

        code, _ = self.run_port("--revision", second)

        self.assertEqual(0, code)
        lock = self.lock()
        self.assertEqual(second, lock["sources"]["owner"]["revision"])
        self.assertEqual(OTHER_REVISION, lock["sources"]["other"]["revision"])
        # A file the source removed is removed here too.
        self.assertEqual(
            {"SKILL.md", "references/a.md", "references/b.md"},
            set(PORT.local_files(self.skill)),
        )
        self.assertEqual(b"# A, revised\n", (self.skill / "references/a.md").read_bytes())
        for record in PORT.REVISION_RECORDS:
            with self.subTest(record=record):
                self.assertEqual(
                    f"Ported at `{second}`.\n", (self.root / record).read_text()
                )
        self.assertEqual(0, self.run_port("--check")[0])

    def test_records_that_cannot_be_told_apart_are_left_to_a_person(self) -> None:
        self.run_port()
        history = f"Taken in at `{self.first}`. Still pinned to `{self.first}`.\n"
        (self.root / "PROVENANCE.md").write_text(history)
        lock = self.lock()
        lock["sources"]["other"]["revision"] = self.first
        self.write_lock(lock)
        self.write_source("references/a.md", "# A, revised\n")
        second = self.publish("second")

        code, output = self.run_port("--revision", second)

        self.assertEqual(0, code)
        lock = self.lock()
        self.assertEqual(second, lock["sources"]["owner"]["revision"])
        # Another source shares the old commit, and its mentions look the same.
        self.assertEqual(self.first, lock["sources"]["other"]["revision"])
        self.assertEqual(history, (self.root / "PROVENANCE.md").read_text())
        self.assertIn("PROVENANCE.md by hand", output)

    def test_a_record_naming_the_old_revision_twice_is_left_to_a_person(self) -> None:
        self.run_port()
        history = f"PR 1 took it in at `{self.first}`. Pinned to `{self.first}`.\n"
        (self.root / "PROVENANCE.md").write_text(history)
        self.write_source("references/a.md", "# A, revised\n")
        second = self.publish("second")

        code, output = self.run_port("--revision", second)

        self.assertEqual(0, code)
        self.assertEqual(history, (self.root / "PROVENANCE.md").read_text())
        self.assertIn("PROVENANCE.md by hand", output)
        self.assertIn(second, (self.root / "THIRD_PARTY_NOTICES.md").read_text())

    def test_a_refusal_changes_nothing(self) -> None:
        self.run_port()
        self.write_source("references/a.md", "# A, revised\n")
        second = self.publish("second")
        lock = self.lock()
        # The old digest now occurs twice, so it cannot be replaced safely. This
        # refusal comes after the source is read and the new texts are planned.
        lock["skills"]["local"]["note"] = lock["skills"]["demo"]["contentSha256"]
        self.write_lock(lock)
        before = self.snapshot()

        for arguments in (
            ("--revision", second),
            ("--revision", "abc123"),
            ("--revision", "f" * 40),
        ):
            with self.subTest(arguments=arguments):
                self.assertEqual(2, self.run_port(*arguments)[0])
                self.assertEqual(before, self.snapshot())

    def test_an_interrupted_write_is_reported_and_a_rerun_completes_it(self) -> None:
        self.run_port()
        self.write_source("references/a.md", "# A, revised\n")
        second = self.publish("second")
        notices = self.root / "THIRD_PARTY_NOTICES.md"
        notices.chmod(0o444)

        code, output = self.run_port("--revision", second)

        self.assertEqual(2, code)
        self.assertIn("writing stopped part-way", output)
        # The lock is written last, so the half-way state is not presented as done.
        self.assertEqual(self.first, self.lock()["sources"]["owner"]["revision"])

        notices.chmod(0o644)
        self.assertEqual(0, self.run_port("--revision", second)[0])
        self.assertEqual(second, self.lock()["sources"]["owner"]["revision"])
        self.assertIn(second, notices.read_text())
        self.assertEqual(0, self.run_port("--check")[0])

    def test_only_a_ported_skill_with_its_own_source_can_be_ported(self) -> None:
        lock = self.lock()
        lock["skills"]["demo"]["disposition"] = "adapted"
        self.write_lock(lock)
        code, output = self.run_port()
        self.assertEqual(2, code)
        self.assertIn("is not a ported skill", output)

        lock["skills"]["demo"]["disposition"] = "ported"
        for kind, component, contract in (
            ("skills", "local", {"lineage": [{"source": "owner", "sourcePath": "y"}]}),
            ("agents", "helper", {"source": ["other", "owner"]}),
        ):
            with self.subTest(kind=kind):
                changed = json.loads(json.dumps(lock))
                changed[kind].setdefault(component, {}).update(contract)
                self.write_lock(changed)
                code, output = self.run_port()
                self.assertEqual(2, code)
                self.assertIn(f"source owner is shared with {component}", output)

    def test_a_symlink_in_the_source_is_refused(self) -> None:
        (self.source / "skills/demo/references/link.md").symlink_to("a.md")
        linked = self.publish("symlink")

        code, output = self.run_port("--revision", linked)

        self.assertEqual(2, code)
        self.assertIn("is not a regular file in the source", output)

    def test_the_shipped_ported_skill_matches_its_lock(self) -> None:
        lock = json.loads((ROOT / "policy/content-lock.json").read_text())
        ported = {
            skill_id: contract
            for skill_id, contract in lock["skills"].items()
            if contract["disposition"] == "ported"
        }
        self.assertIn("aksel-builder", ported)
        for skill_id, contract in ported.items():
            with self.subTest(skill=skill_id):
                files = PORT.local_files(ROOT / "plugin/skills" / skill_id)
                self.assertEqual(contract["contentSha256"], PORT.content_digest(files))


if __name__ == "__main__":
    unittest.main()
