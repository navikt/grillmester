#!/usr/bin/env python3
"""Detect newer OpenCode/Copilot CLI releases than the reviewed local pins.

The explicit local flow is release-gated to one exact reviewed client
combination. This watch compares the launcher's pins with the versions Homebrew
currently distributes and keeps at most one open tracking issue for client
drift. Maintainers can therefore select a reviewed baseline on their cadence
instead of chasing every upstream release. It never edits pins, digests, or
policy itself: bumping the reviewed combination stays a human-reviewed change
through the release gates.

cplt is deliberately not watched here; its releases come from navikt's own
pipeline and land together with a Grillmester release.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import sys
import urllib.request
from pathlib import Path
from typing import Any, Callable, Sequence

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "scripts/grillmester.py"
OPENCODE_API = "https://formulae.brew.sh/api/formula/opencode.json"
COPILOT_API = "https://formulae.brew.sh/api/cask/copilot-cli.json"
GITHUB_API = "https://api.github.com"
USER_AGENT = "grillmester-upstream-client-watch"
ISSUE_TITLE_PREFIX = "Re-gate local clients:"
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
DARWIN_SYSTEM_CA = Path("/etc/ssl/cert.pem")

FetchJson = Callable[..., Any]


class WatchError(RuntimeError):
    """Raised when the upstream watch cannot produce a trustworthy answer."""


def tls_context() -> ssl.SSLContext:
    """Use macOS' system trust store when python.org Python has no CA bundle."""

    default_paths = ssl.get_default_verify_paths()
    if (
        sys.platform == "darwin"
        and default_paths.cafile is None
        and DARWIN_SYSTEM_CA.is_file()
    ):
        return ssl.create_default_context(cafile=str(DARWIN_SYSTEM_CA))
    return ssl.create_default_context()


def parse_pins(launcher_text: str) -> tuple[str, str]:
    opencode = re.search(
        r'^REVIEWED_LOCAL_OPENCODE_VERSION = "(\d+(?:\.\d+)*)"',
        launcher_text,
        re.M,
    )
    copilot = re.search(
        r"^REVIEWED_LOCAL_COPILOT_VERSION = \((\d+), (\d+), (\d+)\)",
        launcher_text,
        re.M,
    )
    if opencode is None or copilot is None:
        raise WatchError(
            "could not parse the reviewed client pins from scripts/grillmester.py"
        )
    return opencode.group(1), ".".join(copilot.groups())


def version_tuple(value: str, *, label: str) -> tuple[int, ...]:
    if re.fullmatch(r"\d+(?:\.\d+)*", value) is None:
        raise WatchError(f"unexpected {label} version format: {value!r}")
    return tuple(int(part) for part in value.split("."))


def fetch_json(url: str, *, token: str | None = None) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    try:
        with urllib.request.urlopen(
            request, timeout=30, context=tls_context()
        ) as response:
            payload = response.read(MAX_RESPONSE_BYTES + 1)
    except OSError as exc:
        raise WatchError(f"could not fetch {url}: {exc}") from exc
    if len(payload) > MAX_RESPONSE_BYTES:
        raise WatchError(f"response from {url} exceeds the size safety limit")
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WatchError(f"response from {url} is not valid UTF-8 JSON") from exc


def send_json(
    url: str, body: dict[str, Any], *, token: str, method: str
) -> Any:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        method=method,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read(MAX_RESPONSE_BYTES).decode("utf-8"))
    except OSError as exc:
        action = "create" if method == "POST" else "update"
        raise WatchError(f"could not {action} tracking issue: {exc}") from exc


def post_json(url: str, body: dict[str, Any], *, token: str) -> Any:
    return send_json(url, body, token=token, method="POST")


def patch_json(url: str, body: dict[str, Any], *, token: str) -> Any:
    return send_json(url, body, token=token, method="PATCH")


def upstream_versions(fetch: FetchJson) -> tuple[str, str]:
    formula = fetch(OPENCODE_API)
    try:
        opencode = str(formula["versions"]["stable"])
    except (KeyError, TypeError) as exc:
        raise WatchError("Homebrew formula response has no stable version") from exc
    cask = fetch(COPILOT_API)
    raw = cask.get("version") if isinstance(cask, dict) else None
    if not isinstance(raw, str) or not raw:
        raise WatchError("Homebrew cask response has no version")
    # Casks may append a checkpoint after a comma; only the leading dotted
    # numeric part is the client version.
    copilot = raw.split(",", 1)[0]
    version_tuple(opencode, label="OpenCode")
    version_tuple(copilot, label="Copilot CLI")
    return opencode, copilot


def issue_title(opencode: str, copilot: str) -> str:
    return f"{ISSUE_TITLE_PREFIX} OpenCode {opencode} / Copilot CLI {copilot}"


def issue_body(
    *, pinned_opencode: str, pinned_copilot: str, opencode: str, copilot: str
) -> str:
    return (
        "Homebrew now distributes a client combination newer than the reviewed "
        "local-mode pins, so `grillmester local` fails closed on upgraded "
        "machines until the combination is re-gated.\n\n"
        f"| Client | Reviewed pin | Homebrew upstream |\n"
        f"| --- | --- | --- |\n"
        f"| OpenCode | {pinned_opencode} | {opencode} |\n"
        f"| Copilot CLI | {pinned_copilot} | {copilot} |\n\n"
        "Re-gating checklist (see docs/release-runbook.md):\n\n"
        "- [ ] Review upstream release notes for sandbox-, argument-, secret- "
        "or discovery-relevant changes\n"
        "- [ ] Select the client baseline to certify; it may skip intermediate "
        "upstream releases\n"
        "- [ ] Bump `REVIEWED_LOCAL_OPENCODE_VERSION` / "
        "`REVIEWED_LOCAL_COPILOT_VERSION` in scripts/grillmester.py and the "
        "expected versions in scripts/smoke_grillmester_local.py and "
        "scripts/manage_opencode.py\n"
        "- [ ] Refresh the pinned artifact digests used by the workflows and "
        "the lifecycle manager\n"
        "- [ ] Run the macOS compatibility gates and the full local smoke "
        "against the new binaries\n"
        "- [ ] Ship a Grillmester release so `brew upgrade` restores local "
        "mode\n\n"
        "Opened automatically by the upstream client watch; it never changes "
        "pins itself."
    )


def open_tracking_issue(
    repository: str, *, token: str, fetch: FetchJson
) -> dict[str, Any] | None:
    for page_number in range(1, 11):
        page = fetch(
            f"{GITHUB_API}/repos/{repository}/issues?state=open&per_page=100"
            f"&page={page_number}",
            token=token,
        )
        if not isinstance(page, list):
            raise WatchError("issue listing response is not a list")
        for issue in page:
            if (
                isinstance(issue, dict)
                and "pull_request" not in issue
                and isinstance(issue.get("title"), str)
                and issue["title"].startswith(ISSUE_TITLE_PREFIX)
            ):
                number = issue.get("number")
                if type(number) is not int or number <= 0:
                    raise WatchError("tracking issue has no valid issue number")
                return issue
        if len(page) < 100:
            return None
    raise WatchError("tracking issue search exceeded 1000 open issues")


def main(
    argv: Sequence[str] | None = None,
    *,
    fetch: FetchJson = fetch_json,
    poster: Callable[..., Any] = post_json,
    updater: Callable[..., Any] = patch_json,
    environment: dict[str, str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="print drift status without creating a tracking issue",
    )
    arguments = parser.parse_args(argv)
    environment = dict(os.environ) if environment is None else environment

    pinned_opencode, pinned_copilot = parse_pins(
        LAUNCHER.read_text(encoding="utf-8")
    )
    opencode, copilot = upstream_versions(fetch)
    drift = version_tuple(opencode, label="OpenCode") > version_tuple(
        pinned_opencode, label="pinned OpenCode"
    ) or version_tuple(copilot, label="Copilot CLI") > version_tuple(
        pinned_copilot, label="pinned Copilot CLI"
    )
    print(f"Reviewed pins: OpenCode {pinned_opencode}, Copilot CLI {pinned_copilot}")
    print(f"Homebrew upstream: OpenCode {opencode}, Copilot CLI {copilot}")
    if not drift:
        print("Reviewed pins match Homebrew upstream; nothing to re-gate.")
        return 0
    title = issue_title(opencode, copilot)
    if arguments.report_only:
        print(f"Drift detected; would track as: {title}")
        return 0
    repository = environment.get("GITHUB_REPOSITORY", "")
    token = environment.get("GITHUB_TOKEN", "")
    if not repository or not token:
        raise WatchError(
            "GITHUB_REPOSITORY and GITHUB_TOKEN are required to open the "
            "tracking issue; use --report-only for a local check"
        )
    body = issue_body(
        pinned_opencode=pinned_opencode,
        pinned_copilot=pinned_copilot,
        opencode=opencode,
        copilot=copilot,
    )
    existing = open_tracking_issue(repository, token=token, fetch=fetch)
    if existing is not None:
        if existing.get("title") == title and existing.get("body") == body:
            print(f"Tracking issue already current: {title}")
            return 0
        number = existing["number"]
        updated = updater(
            f"{GITHUB_API}/repos/{repository}/issues/{number}",
            {"title": title, "body": body},
            token=token,
        )
        url = updated.get("html_url") if isinstance(updated, dict) else None
        print(f"Updated tracking issue: {url or title}")
        return 0
    created = poster(
        f"{GITHUB_API}/repos/{repository}/issues",
        {
            "title": title,
            "body": body,
        },
        token=token,
    )
    url = created.get("html_url") if isinstance(created, dict) else None
    print(f"Opened tracking issue: {url or title}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except WatchError as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(2)
