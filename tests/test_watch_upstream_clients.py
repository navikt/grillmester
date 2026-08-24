from __future__ import annotations

import importlib.util
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "grillmester_watch_upstream_clients",
    ROOT / "scripts/watch_upstream_clients.py",
)
assert SPEC is not None and SPEC.loader is not None
WATCH = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = WATCH
SPEC.loader.exec_module(WATCH)


def fake_fetch(responses: dict[str, object]):
    calls: list[str] = []

    def fetch(url: str, *, token: str | None = None) -> object:
        calls.append(url)
        return responses[url.split("?", 1)[0]]

    return fetch, calls


class PinParsingTests(unittest.TestCase):
    def test_pins_parse_from_the_real_launcher(self) -> None:
        opencode, copilot = WATCH.parse_pins(
            (ROOT / "scripts/grillmester.py").read_text(encoding="utf-8")
        )

        cli_spec = importlib.util.spec_from_file_location(
            "grillmester_cli_watch_check", ROOT / "scripts/grillmester.py"
        )
        assert cli_spec is not None and cli_spec.loader is not None
        cli = importlib.util.module_from_spec(cli_spec)
        sys.modules[cli_spec.name] = cli
        try:
            cli_spec.loader.exec_module(cli)
            self.assertEqual(cli.REVIEWED_LOCAL_OPENCODE_VERSION, opencode)
            self.assertEqual(
                ".".join(str(part) for part in cli.REVIEWED_LOCAL_COPILOT_VERSION),
                copilot,
            )
        finally:
            sys.modules.pop(cli_spec.name, None)

    def test_missing_pins_fail_closed(self) -> None:
        with self.assertRaisesRegex(WATCH.WatchError, "reviewed client pins"):
            WATCH.parse_pins("REVIEWED_LOCAL_OPENCODE_VERSION = None\n")


class UpstreamParsingTests(unittest.TestCase):
    def test_python_org_macos_uses_the_system_ca_without_disabling_tls(self) -> None:
        context = object()
        with (
            mock.patch.object(WATCH.sys, "platform", "darwin"),
            mock.patch.object(
                WATCH.ssl,
                "get_default_verify_paths",
                return_value=SimpleNamespace(cafile=None),
            ),
            mock.patch.object(
                type(WATCH.DARWIN_SYSTEM_CA), "is_file", return_value=True
            ),
            mock.patch.object(
                WATCH.ssl,
                "create_default_context",
                return_value=context,
            ) as create_context,
        ):
            self.assertIs(context, WATCH.tls_context())

        create_context.assert_called_once_with(cafile="/etc/ssl/cert.pem")

    def test_cask_checkpoint_suffix_is_stripped(self) -> None:
        fetch, _ = fake_fetch(
            {
                WATCH.OPENCODE_API: {"versions": {"stable": "1.19.0"}},
                WATCH.COPILOT_API: {"version": "1.0.81,abcdef"},
            }
        )
        self.assertEqual(("1.19.0", "1.0.81"), WATCH.upstream_versions(fetch))

    def test_unexpected_version_formats_fail_closed(self) -> None:
        fetch, _ = fake_fetch(
            {
                WATCH.OPENCODE_API: {"versions": {"stable": "latest"}},
                WATCH.COPILOT_API: {"version": "1.0.81"},
            }
        )
        with self.assertRaisesRegex(WATCH.WatchError, "OpenCode version format"):
            WATCH.upstream_versions(fetch)


class DriftReportingTests(unittest.TestCase):
    def run_main(
        self,
        *,
        opencode: str,
        copilot: str,
        open_issues: list[dict[str, str]] | None = None,
        argv: list[str] | None = None,
        environment: dict[str, str] | None = None,
    ) -> tuple[
        int,
        str,
        list[tuple[str, dict[str, object]]],
        list[tuple[str, dict[str, object]]],
    ]:
        pinned_opencode, pinned_copilot = WATCH.parse_pins(
            (ROOT / "scripts/grillmester.py").read_text(encoding="utf-8")
        )
        del pinned_opencode, pinned_copilot
        fetch, _ = fake_fetch(
            {
                WATCH.OPENCODE_API: {"versions": {"stable": opencode}},
                WATCH.COPILOT_API: {"version": copilot},
                f"{WATCH.GITHUB_API}/repos/navikt/grillmester/issues": (
                    open_issues or []
                ),
            }
        )
        posts: list[tuple[str, dict[str, object]]] = []
        updates: list[tuple[str, dict[str, object]]] = []

        def poster(url: str, body: dict[str, object], *, token: str) -> object:
            posts.append((url, body))
            return {"html_url": "https://example.invalid/issue/1"}

        def updater(url: str, body: dict[str, object], *, token: str) -> object:
            updates.append((url, body))
            return {"html_url": "https://example.invalid/issue/17"}

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            status = WATCH.main(
                argv or [],
                fetch=fetch,
                poster=poster,
                updater=updater,
                environment=environment
                if environment is not None
                else {
                    "GITHUB_REPOSITORY": "navikt/grillmester",
                    "GITHUB_TOKEN": "test-token",
                },
            )
        return status, stdout.getvalue(), posts, updates

    def test_matching_pins_open_no_issue(self) -> None:
        pinned_opencode, pinned_copilot = WATCH.parse_pins(
            (ROOT / "scripts/grillmester.py").read_text(encoding="utf-8")
        )
        status, output, posts, updates = self.run_main(
            opencode=pinned_opencode, copilot=pinned_copilot
        )
        self.assertEqual(0, status)
        self.assertIn("nothing to re-gate", output)
        self.assertEqual([], posts)
        self.assertEqual([], updates)

    def test_newer_upstream_opens_one_tracking_issue(self) -> None:
        status, output, posts, updates = self.run_main(
            opencode="99.0.0", copilot="1.0.80"
        )
        self.assertEqual(0, status)
        self.assertEqual(1, len(posts))
        url, body = posts[0]
        self.assertIn("/repos/navikt/grillmester/issues", url)
        self.assertIn("OpenCode 99.0.0", str(body["title"]))
        self.assertIn("docs/release-runbook.md", str(body["body"]))
        self.assertIn("never changes pins itself", str(body["body"]))
        self.assertIn("Opened tracking issue", output)
        self.assertEqual([], updates)

    def test_existing_open_issue_is_not_duplicated(self) -> None:
        title = WATCH.issue_title("99.0.0", "1.0.80")
        pinned_opencode, pinned_copilot = WATCH.parse_pins(
            (ROOT / "scripts/grillmester.py").read_text(encoding="utf-8")
        )
        body = WATCH.issue_body(
            pinned_opencode=pinned_opencode,
            pinned_copilot=pinned_copilot,
            opencode="99.0.0",
            copilot="1.0.80",
        )
        status, output, posts, updates = self.run_main(
            opencode="99.0.0",
            copilot="1.0.80",
            open_issues=[{"number": 17, "title": title, "body": body}],
        )
        self.assertEqual(0, status)
        self.assertEqual([], posts)
        self.assertEqual([], updates)
        self.assertIn("already current", output)

    def test_older_open_drift_issue_coalesces_a_new_upstream_combination(self) -> None:
        status, output, posts, updates = self.run_main(
            opencode="99.0.0",
            copilot="1.0.99",
            open_issues=[
                {
                    "number": 17,
                    "title": WATCH.issue_title("1.19.0", "1.0.81"),
                    "body": "stale body",
                },
            ],
        )
        self.assertEqual(0, status)
        self.assertEqual([], posts)
        self.assertEqual(1, len(updates))
        update_url, update_body = updates[0]
        self.assertTrue(update_url.endswith("/issues/17"))
        self.assertIn("OpenCode 99.0.0", str(update_body["title"]))
        self.assertIn("Updated tracking issue", output)

    def test_report_only_never_needs_credentials(self) -> None:
        status, output, posts, updates = self.run_main(
            opencode="99.0.0",
            copilot="1.0.80",
            argv=["--report-only"],
            environment={},
        )
        self.assertEqual(0, status)
        self.assertEqual([], posts)
        self.assertEqual([], updates)
        self.assertIn("would track as", output)

    def test_drift_without_credentials_fails_closed(self) -> None:
        with self.assertRaisesRegex(WATCH.WatchError, "GITHUB_REPOSITORY"):
            self.run_main(opencode="99.0.0", copilot="1.0.80", environment={})


if __name__ == "__main__":
    unittest.main()
