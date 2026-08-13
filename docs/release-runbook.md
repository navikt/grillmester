# Release and rollback runbook

Grillmester has an immutable, two-step release identity:

1. `v<manifest-semver>` points to a **catalog-only commit** reachable from the
   `marketplace` branch.
2. Its only package is `grillmester` from `plugin`. The catalog's `source.sha`
   points to the exact source commit reachable from `main`.

The tag identifies the catalog, not the source tree. GitHub's source archive
for the release therefore contains only `.github/plugin/marketplace.json`.
Install through the Grillmester marketplace; do not use the release archive.
Never move, replace, delete, or force-update a release tag.

## Workflows and trust boundary

Three workflows have deliberately separate jobs:

- **Publish marketplace catalog** runs after plugin or release-contract
  changes land on `main`. A read-only job validates and seals the generated
  one-package catalog before any third-party smoke tooling
  runs. A one-step write job revalidates the sealed bytes, creates a
  catalog-only child of the current `marketplace` tip, and performs a normal
  fast-forward push. It has no manual-dispatch entry point.
- **Validate immutable release** is an optional, read-only manual preflight.
  Dispatch it from `main` with an exact catalog SHA. It cannot create a tag or
  release.
- **Publish reviewed release request** is the only release publisher. It runs
  when a reviewed `.github/release-request.json` change lands on `main`,
  validates the complete chain and stages the exact catalog bytes and
  source-pinned payload in an isolated local smoke, then waits at the protected
  `grillmester-release` environment. Its only write-capable job contains one
  fixed inline publication step with no checkout, action, package install, or
  repository-script execution. After publication, a read-only job verifies the
  tag target and installs from the actual remote `v<version>` ref.

The release-request PR, protected `main`, rulesets, and environment approval
are process and accidental-misdispatch controls. A normal repository
`GITHUB_TOKEN` is not a cryptographic per-workflow identity: a ruleset bypass
granted broadly to GitHub Actions cannot prove that only one workflow used it.
If strict separation from every repository writer is required, replace the
write token with a dedicated GitHub App credential exposed only through the
protected release environment, and make that App the sole tag/release ruleset
bypass actor. Do not claim strict actor separation until that hardening is in
place.

## One-time repository controls

An administrator must configure and verify all of these before the first
release:

- Protect `main`; require reviewed PRs for workflow, release-contract, and
  `.github/release-request.json` changes. A release-request PR should change
  only the request file.
- Protect `marketplace` from deletion and force-pushes. Limit ordinary updates
  to the catalog publisher's automation path, subject to the trust boundary
  above.
- Add `v*` tag rules that prevent update and deletion. Restrict creation to the
  approved release automation identity.
- Enable immutable GitHub Releases if the repository setting is available.
- Create the `grillmester-release` environment, restrict deployments to
  `main`, require a reviewer other than the request author, enable
  prevent-self-review, and disable administrator bypass.

Merely naming an environment in YAML is not an approval gate: GitHub can create
an unconfigured environment automatically. Verify the settings in GitHub
before merging a release request. All three workflows share the
`publish-grillmester-marketplace` concurrency group so selection and
publication cannot race the catalog publisher.

## Release a candidate

1. Set `plugin/plugin.json.version` to a strict prerelease SemVer, for example
   `0.3.0-poc.2`. Build metadata is not accepted, and a version must never be
   reused for different payload bytes.
2. Merge that source change normally. Wait for **Publish marketplace catalog**
   and resolve the exact catalog-only commit containing the version:

   ```bash
   git fetch origin main marketplace
   git log -1 --format=%H origin/marketplace
   git show MARKETPLACE_SHA:.github/plugin/marketplace.json
   ```

3. Optionally dispatch **Validate immutable release** from the `main` branch
   with `channel=rc`, the full `catalog_sha`, and an empty `rc_tag`. A run from
   another selected ref fails rather than being skipped. This preflight is
   read-only and is not a publication request.
4. Open a separate PR that changes only `.github/release-request.json`:

   ```json
   {
     "schemaVersion": 1,
     "requestId": "v0.3.0-poc.2-1",
     "channel": "rc",
     "catalogSha": "0123456789abcdef0123456789abcdef01234567",
     "rcTag": ""
   }
   ```

   Use the real 40-character catalog SHA. `requestId` is a lowercase audit and
   retry identifier; increment its final component when the exact same release
   must be requested again.
5. After review, merge the request. **Publish reviewed release request** binds
   the request to current `origin/main`, checks that the catalog is reachable
   from `marketplace`, requires the complete merged push range to change only
   the request file, checks that `source.sha` is reachable from `main`,
   requires an exact catalog-only tree, and regenerates the one-entry catalog
   byte-for-byte from the release contract and plugin manifest at that source.
   It then stages and verifies those exact catalog bytes and the source-pinned
   Grillmester payload locally before seeking environment approval. A raw
   catalog SHA is not passed to Copilot as a marketplace ref; the CLI accepts a
   branch or tag there.
6. The environment reviewer compares the request, run summary, catalog SHA,
   source SHA, and derived `v<manifest-semver>` tag before approving.

The write step fetches and revalidates the refs again immediately before it
mutates GitHub. It creates an annotated tag at the catalog commit and a GitHub
prerelease with `--verify-tag` and `latest=false`. The following read-only
`remote-smoke` job peels the published tag back to the expected catalog commit,
installs from `navikt/grillmester#v<version>`, byte-verifies the 7-agent/44-skill
payload, and uninstalls it. A failed post-publication smoke stops promotion and
requires a new corrective version; tags are never moved.

## Promote a reviewed candidate to stable

Stable is a new version, source commit, catalog commit, tag, and GitHub Release;
it is never a second label on the RC catalog. Create a source commit whose
plugin manifest uses the stable version, such as `0.3.0`. Apart from the exact
`version` value in `plugin/plugin.json`, the package payload and manifest format
must be byte-identical to the named candidate. The release contract must also
be byte-identical. Let the catalog publisher create the new stable-versioned
catalog.

Optionally run the read-only validator with `channel=stable`, the new catalog
SHA, and the reviewed prerelease tag. Then merge a separate request-file PR:

```json
{
  "schemaVersion": 1,
  "requestId": "v0.3.0-1",
  "channel": "stable",
  "catalogSha": "fedcba9876543210fedcba9876543210fedcba98",
  "rcTag": "v0.3.0-poc.2"
}
```

The publisher peels the named RC tag, verifies its prerelease, requires the RC
and stable versions to share `major.minor.patch`, verifies both catalog/source chains, and
allows no payload change beyond the manifest version. It then creates the new
stable tag and release. Never retag the RC catalog.

## Idempotency and interrupted publication

The publisher never moves an existing tag:

- no tag and no release: create both;
- correct tag but no release: keep the tag and create the missing release;
- exact tag and exact release metadata: succeed as a no-op;
- an existing tag at another catalog, or mismatched release metadata: fail.

Rerun the failed push workflow while its request commit is still current
`origin/main`. If `main` has moved, open a new request-only PR with the same
channel/catalog/RC values and a new `requestId`. This preserves a reviewable
retry without changing or reusing immutable release content.

## Rollback and containment

Do not rewrite a bad release. Stop adoption and:

1. Revert each managed consumer's marketplace `ref` to the last reviewed tag.
2. For a personal install, uninstall `grillmester`, add/update the marketplace
   at the previous tag, and install `grillmester` again.
3. Publish a new version containing the correction. Catalog version reuse is
   rejected, including reuse of an older historical version.

If the publisher is wedged by a malformed `marketplace` tip, do not force-push
or edit the branch manually. Disable release publication, preserve the bad SHA
as incident evidence, fix the publisher on `main`, and use a reviewed recovery
through the protected automation identity. Re-enable it only after generator,
validator, remote install smoke, and history/version guards pass.

Record the catalog SHA, source SHA, tags, consumer refs, request ID, and recovery
actions in the incident. Repinning does not make an already-started agent
session forget loaded content; restart the affected Copilot session.
