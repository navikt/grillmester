# Release and rollback runbook

Grillmester has an immutable, two-step release identity:

1. `v<manifest-semver>` points to a **catalog-only commit** reachable from the
   `marketplace` branch.
2. Its only package is `grillmester` from `plugin`. The catalog's `source.sha`
   points to the exact source commit reachable from `main`.

The tag identifies the catalog, not the source tree. GitHub's automatically
generated source archive for the release therefore contains only
`.github/plugin/marketplace.json`; it is not an installation artifact. Install
the Copilot plugin through the Grillmester marketplace. Install OpenCode from
the separately attached, deterministic `tar.gz` and its detached `.sha256` from
the same GitHub Release. Never move, replace, delete, or force-update a release
tag or replace an existing release asset.

## Workflows and trust boundary

Three workflows have deliberately separate jobs:

- **Publish marketplace catalog** is an explicit maintainer dispatch from
  current `main` with an exact source SHA reachable from `origin/main`. A
  read-only job validates that trusted dispatch context, regenerates and seals
  the one-package catalog from that exact source before any third-party smoke
  tooling runs. The selected source commit's own tooling and tests execute only
  in that read-only validation job. The one-step write job is a fresh runner:
  it executes no selected-source code, revalidates the sealed bytes, creates a
  catalog-only child of the current `marketplace` tip, and performs a normal
  fast-forward push. Its following read-only smoke installs from the actual
  floating `marketplace` ref.
- **Validate immutable release** is an optional, read-only manual preflight.
  Dispatch it from `main` with an exact catalog SHA. It cannot create a tag or
  release.
- **Publish reviewed release request** is the only release publisher. It runs
  when a reviewed `.github/release-request.json` change lands on `main`,
  validates the complete chain and stages the exact catalog bytes and
  source-pinned payload in an isolated local smoke. The read-only validation
  job also builds the OpenCode bundle twice, requires byte identity, verifies
  `DISTRIBUTION-MANIFEST.json`, and seals the exact `tar.gz`, detached checksum
  and release notes. A separate read-only job retrieves the exact immutable
  artifact ID and uses fixed workflow-owned code to match every archive file,
  mode, manifest entry, and canonical archive property to immutable Git blobs
  at the selected source SHA. Separate Copilot and genuine macOS compatibility
  jobs must also pass. The macOS job verifies the pinned native OpenCode and
  cplt archives and executables before their first execution, runs the native
  and cplt runtime smokes, proves allowed-loopback/blocked-host raw sockets under
  forced proxy policy, and launches the installed manager through `local-only`
  with an explicit local provider, exact loopback base URL, model ID, and
  positive context/output limits.
  Only after all of those jobs succeed does the workflow wait at the protected
  `grillmester-release` environment. The two asset files cross
  that boundary in one immutable
  Actions artifact; only its exact artifact ID, server digest, file digests,
  sizes and names cross as scalar outputs. Its write-capable job contains two
  fixed inline steps with no checkout, action, package install, or repository-
  script execution. The first uses the environment's Administration:read token
  only to require that immutable GitHub Releases are enabled. The second alone
  receives the ordinary contents-write token, fetches only the sealed artifact
  ID, binds it back to the same workflow run and digest, requires exactly the
  two expected files, and may therefore only publish the already source-bound
  sealed bytes without executing selected-source code. It finally requires the
  published release object (and an RC used for stable promotion) to report
  `immutable: true`. After
  publication, a read-only job verifies the tag target, installs from the
  actual remote `v<version>` marketplace ref, downloads and checksum-verifies
  the attached OpenCode asset, and exercises its install contract.

The source reachability control relies on the current linear/squash `main`
history. If merge commits are enabled, strengthen it to require first-parent
membership. If `main` advances during validation or before an idempotent rerun,
the current-main guard fails closed; dispatch a fresh run from current `main`.

### OpenCode asset contract

The asset's `DISTRIBUTION-MANIFEST.json` must bind the selected source SHA,
OpenCode `1.18.20`, cplt `2026.08.17-062831-1008a92`, the inner target manifest
digest, and the complete distribution inventory. Every cplt-backed profile
requires that exact cplt release. The manager and native agents have no runtime
dependency on `nav-pilot-agent`, the Copilot plugin installation, or a Copilot
agent. `--direct` remains an explicit opt-out from cplt sandbox and egress
policy; it is not the default or a `local-only` mode. Passing this release gate
proves the packaged surface and deterministic runtime contract, not quality
parity for an arbitrary local or cloud model.

The committed npm integrity, GitHub Release asset digest, and cplt
`SHA256SUMS` values bind the bytes accepted by the gate. They are not a
separately verified maintainer signature or artifact attestation. The pinned
cplt release is marked mutable upstream, so any later byte replacement fails
against the committed archive and executable digests. Managed Linux cplt is
gated only with its GNU/glibc assets; OpenCode's musl assets do not create a
managed-musl support claim without a corresponding cplt asset.

The release-request PR, protected `main`, rulesets, and environment approval
are process and accidental-misdispatch controls. A normal repository
`GITHUB_TOKEN` is not a cryptographic per-workflow identity: a ruleset bypass
granted broadly to GitHub Actions cannot prove that only one workflow used it.
If strict separation from every repository writer is required, replace the
write token with a dedicated GitHub App credential exposed only through the
protected release environment, and make that App the sole tag/release ruleset
bypass actor. Do not claim strict actor separation until that hardening is in
place. If that future hardening changes bypass actors, deliberately update this
documented ruleset and readback contract. Empty `bypass_actors` is a standing
control: neither normal publisher needs a bypass, and no alternate writer is
authorized to bypass these protections.

## Repository controls

An administrator must maintain and verify these current active controls:

- Protect `main`; require reviewed PRs for workflow, release-contract, and
  `.github/release-request.json` changes. A release-request PR should change
  only the request file.
- Keep the existing active `main` ruleset (ID `20790914`) unchanged, including
  Team `4531825` with `always` bypass. Do not copy, replace, or broaden that
  ruleset as part of marketplace or tag protection.
- In addition to the existing `main` ruleset, maintain exactly two separate
  active repository rulesets for the `marketplace`/`v*` distribution refs, both
  with an empty `bypass_actors` list:

  | Target | `conditions.ref_name.include` | `rules` |
  | --- | --- | --- |
  | `branch` | `["refs/heads/marketplace"]` | `[{"type":"deletion"},{"type":"non_fast_forward"}]` |
  | `tag` | `["refs/tags/v*"]` | `[{"type":"deletion"},{"type":"update"}]` |

  Their effective API shape is `enforcement: "active"`, the target and include
  value shown above, `conditions.ref_name.exclude: []`, the exact target-specific
  rules shown above, and
  `bypass_actors: []`. Ruleset names are administrative labels; the target,
  conditions, rule types, enforcement, and bypass actors are the contract.

  When `protect-release-tags` was created, its REST create request supplied
  `update.parameters.update_allows_fetch_and_merge: false`. GitHub accepted
  that request, but its tag-target detail readback normalizes the rule to
  `{"type":"update"}` without the branch-oriented parameter. The durable
  live/readback contract is therefore the exact tag rule types `deletion` and
  `update`; do not require that parameter to be returned.

  On 2026-08-18, readback verified the following repository-owned active
  rulesets for `navikt/grillmester`: `protect-marketplace-history` (ID
  `20981629`) with branch target `refs/heads/marketplace`, and
  `protect-release-tags` (ID `20981630`) with tag target `refs/tags/v*`.
  Both had source type `Repository`, source `navikt/grillmester`,
  `conditions.ref_name.exclude: []`, and `bypass_actors: []`.
  Effective rules for `marketplace` were exactly `deletion` and
  `non_fast_forward` from ruleset `20981629`. The existing `main` ruleset
  `20790914` and Team `4531825` `always` bypass were unchanged, as confirmed
  by pre- and post-change readback.

  These deliberately minimal rules do not include a `creation` rule. They
  therefore allow the catalog publisher's ordinary fast-forward update of
  `marketplace` and the release publisher's creation of a new `v*` tag, while
  blocking deletion and non-fast-forward movement of `marketplace`. For `v*`
  tags, `deletion` plus `update` blocks every update or retarget. A
  `non_fast_forward` rule alone does not establish that guarantee because
  GitHub's PATCH Git reference endpoint permits a fast-forward reference update
  with `force: false`. No ruleset bypass is needed for either normal publisher
  operation.
- Enable immutable GitHub Releases. The publisher fails closed against
  `GET /repos/navikt/grillmester/immutable-releases` with API version
  `2026-03-10` unless `enabled` is exactly `true`, and it requires the final
  release readback to contain `immutable: true`. On 2026-08-21 the live setting
  read back as `enabled: false`; publication is therefore intentionally blocked
  until an authorized administrator enables it. The workflow never changes the
  setting itself.
- Create the `grillmester-release` environment, restrict deployments to
  `main`, require a reviewer other than the request author, enable
  prevent-self-review, and disable administrator bypass. Store a dedicated
  fine-grained credential named `IMMUTABLE_RELEASES_ADMIN_READ_TOKEN` in that
  environment with Administration **read-only** access to this repository. Do
  not grant it contents write and do not reuse the release publisher token;
  the workflow exposes it only to the read-only immutable-setting preflight.

Merely naming an environment in YAML is not an approval gate: GitHub can create
an unconfigured environment automatically. Verify the settings in GitHub
before merging a release request. All three workflows share the
`publish-grillmester-marketplace` concurrency group so selection and
publication cannot race the catalog publisher.

### Read back the live rules

Use an authenticated repository administrator, or an equivalent caller with
permission to read ruleset bypass actors. `bypass_actors` is returned only to a
caller with write access to the ruleset, so an absent or `null` value is
inconclusive and must never be accepted as an empty list. These commands are
read-only and deliberately request only the fields needed to review the rules;
they neither print credentials nor use verbose HTTP output.

```bash
set -euo pipefail

repository=navikt/grillmester

repository_ruleset_ids="$(
  gh api --paginate "repos/${repository}/rulesets?includes_parents=false" \
    --jq '.[] | .id'
)"

if [[ -z "$repository_ruleset_ids" ]]; then
  printf '%s\n' 'No repository-owned ruleset IDs were returned.' >&2
  exit 1
fi

while IFS= read -r id; do
  detail="$(
    gh api "repos/${repository}/rulesets/${id}" \
      --jq '
        if type == "object" and length > 0 then
          {id, name, target, source_type, source, enforcement, conditions, rules, bypass_actors}
        else
          error("ruleset detail response was empty or not an object")
        end
      '
  )"

  if [[ -z "$detail" ]]; then
    printf 'Ruleset %s returned an empty detail response.\n' "$id" >&2
    exit 1
  fi

  printf '%s\n' "$detail"
done <<< "$repository_ruleset_ids"

printf '%s\n' 'Ruleset summaries, including inherited parent controls:'
gh api --paginate "repos/${repository}/rulesets?includes_parents=true" \
  --jq '.[] | [.id, .name, .target, .source_type, .source, .enforcement] | @tsv'
```

The first list call is limited to repository-owned rulesets and captures all
returned IDs before any detail lookup. It fails closed if enumeration, any
sequential detail request, or projection fails, or if the repository-owned ID
list or a detail object is empty. The detail projection includes `source_type`
and `source`; require each of the two new rulesets to have
`source_type: "Repository"` and `source: "navikt/grillmester"`. Select them by
`target` and `conditions.ref_name.include`, not by name. For each, inspect:

- `enforcement` is `active`;
- `conditions.ref_name.include` is exactly `refs/heads/marketplace` for the
  branch ruleset or exactly `refs/tags/v*` for the tag ruleset, and `exclude`
  is empty;
- the branch rules are exactly `deletion` and `non_fast_forward`, without extra
  rule types;
- the tag rules are exactly `deletion` and `update`, without extra rule types;
  and
- `bypass_actors` is empty.

The second list call intentionally uses `includes_parents=true` and prints only
summary fields, including `source_type` and `source`, so inherited organization
or parent controls remain visible. Do not send those inherited IDs to the
repository ruleset-detail endpoint. A failed or empty repository detail
response is inconclusive; do not infer the rule, parameter, source, or bypass
state from a list response. An absent or `null` `bypass_actors` value remains
inconclusive and must not be accepted as an empty list.

Also inspect ruleset `20790914`: it remains the existing `main` protection and
still lists Team actor ID `4531825` with bypass mode `always`. The two maintained
rulesets must not add a bypass actor or alter this main-team bypass.

As a cross-check, inspect the effective rules for `marketplace`; this confirms
the applicable branch rule types but does not replace the per-ID detail
readback of conditions or bypass actors:

```bash
repository=navikt/grillmester

gh api "repos/${repository}/rules/branches/marketplace" --jq '.[] | .type'
```

### Post-activation proof and accepted residual risk

Prove the controls only through normal, legitimate publisher operations:

1. During a planned catalog promotion, dispatch **Publish marketplace catalog**
   from current `main` with a new, valid source SHA and confirm its normal
   fast-forward push to `marketplace` succeeds.
2. During a planned reviewed release, let **Publish reviewed release request**
   create its new `v<version>` tag and confirm its existing remote smoke
   succeeds.
3. Repeat the readback above after each activation or ruleset change. A
   successful publisher run and API readback together prove the allowed paths
   and configured restrictions. The 2026-08-18 readback is configuration
   evidence only; it does not prove that either controlled publisher has run.

Do not test deletion, force-push, or tag movement against production refs. The
readback is safe configuration evidence for those blocked operations, not an
empirical demonstration against the production refs; use a disposable
repository if a destructive behavior demonstration is ever required.

The accepted residual risk is that repository writers and workflows holding
`contents: write` can still append valid fast-forward history to `marketplace`
or create new matching `v*` tags. These two rulesets prevent destructive ref
changes to `marketplace` and every update or retarget of matching tags; they do
not prevent tag creation or valid branch-history append. There is no dedicated
GitHub App in scope, so the normal `GITHUB_TOKEN` publisher is not a
cryptographic per-workflow identity and the rules cannot distinguish it from
another authorized repository writer. Existing workflow validation, protected
`main`, and environment review remain defense-in-depth controls, not proof of
strict writer separation.

## Release a candidate

1. Set `plugin/plugin.json.version` to a strict prerelease SemVer, for example
   `0.3.0-rc.1`. Build metadata is not accepted, and a version must never be
   reused for different payload bytes.
2. Merge that source change normally. From current `main`, explicitly dispatch
   **Publish marketplace catalog** with `channel=rc`, the exact lowercase
   40-character `source_sha` to promote, and an empty `rc_tag`. Wait for it to
   complete, then resolve the exact catalog-only commit containing the version:

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
     "requestId": "v0.3.0-rc.1-1",
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
   Grillmester payload locally, builds the deterministic OpenCode bundle twice,
   and uploads the bundle and detached checksum as one immutable, digest-bound
   workflow artifact before seeking environment approval. A raw
   catalog SHA is not passed to Copilot as a marketplace ref; the CLI accepts a
   branch or tag there. OpenCode does not install from that catalog path; its
   release asset is bound to the same source SHA by
   `DISTRIBUTION-MANIFEST.json`.
6. The environment reviewer compares the request, run summary, catalog SHA,
   source SHA, OpenCode asset SHA-256, and derived `v<manifest-semver>` tag
   before approving.

The read-only asset verifier checks the archive's bounded gzip/tar structure,
canonical manifest, complete inventory, modes, and file bytes against immutable
Git blobs. The write step then fetches and revalidates the refs again immediately
before it mutates GitHub. It resolves the same sealed artifact ID through the
Actions API, requires the expected workflow-run ID and server digest, and checks
the exact inner bytes and detached checksum again. It creates an annotated tag at the catalog commit,
then stages a draft GitHub Release with `--verify-tag`. Only an unpublished
draft may have the two sealed asset names retried with `--clobber`; unexpected
draft assets fail closed. The step downloads and byte-verifies both staged
assets before publishing the draft (`prerelease` and `latest=false` for an RC).
Published assets are never replaced. The following read-only
`remote-smoke` job peels the published tag back to the expected catalog commit,
installs from `navikt/grillmester#v<version>`, byte-verifies the 7-agent/42-skill
Copilot payload, downloads both OpenCode assets, verifies the detached checksum
before safe extraction, and runs the manager's install verification. A failed
post-publication smoke stops promotion and requires a new corrective version;
tags and assets are never replaced.

The floating `marketplace` branch is also the personal CLI auto-update channel.
It advances only after a maintainer explicitly promotes an exact validated
source SHA; an ordinary merge to `main` does not deploy it. Keep an isolated
Copilot home on the previous version, start a new trusted CLI session after
publication, and verify that it advances without an explicit update command.
This is post-deployment evidence and is separate from the immutable-tag smoke.
Use an immutable release tag when rollout must wait for a separate approval.
Record App and VS Code behavior separately; neither may be inferred from the
CLI result.

## Promote a reviewed candidate to stable

Stable is a new version, source commit, catalog commit, tag, and GitHub Release;
it is never a second label on the RC catalog. Create a source commit whose
plugin manifest uses the stable version, such as `0.3.0`. Apart from the exact
`version` value in `plugin/plugin.json`, the package payload and manifest format
must be byte-identical to the named candidate. The release contract must also
be byte-identical. OpenCode distribution inputs — manager, profiles, generated
target and bundle-builder contract — must also be byte-identical between RC and
stable; the outer bundle manifest and checksum are expected to change because
they bind the new stable source SHA. Before either validation or publication can
promote stable, the workflow also downloads the named RC's two public assets,
requires their API and detached digests, rebuilds the RC archive from its exact
source SHA, and requires byte identity. Explicitly dispatch **Publish
marketplace catalog** from current `main` with `channel=stable`, the new stable
source commit as `source_sha`, and the exact reviewed prerelease tag (for
example `v0.3.0-rc.1`) as `rc_tag`. That publisher revalidates the public RC
release, rights approval, source parity, rebuilt RC bundle, API asset digests,
and detached checksum before it creates the new stable-versioned catalog.

Optionally run the read-only validator with `channel=stable`, the new catalog
SHA, and the reviewed prerelease tag. Then merge a separate request-file PR:

```json
{
  "schemaVersion": 1,
  "requestId": "v0.3.0-1",
  "channel": "stable",
  "catalogSha": "fedcba9876543210fedcba9876543210fedcba98",
  "rcTag": "v0.3.0-rc.1"
}
```

The publisher peels the named RC tag, verifies its prerelease, requires the RC
and stable versions to share `major.minor.patch`, verifies both catalog/source chains, and
allows no payload change beyond the manifest version. It then creates the new
stable tag and release. Never retag the RC catalog.

## Idempotency and interrupted publication

The publisher never moves an existing tag:

- no tag and no release: create both;
- correct tag but no release: keep the tag, create a draft, stage and verify the
  two assets, then publish;
- correct tag and an exact or partially uploaded draft containing no unexpected
  asset names: retry the two sealed names, byte-verify them, then publish;
- exact tag, release metadata, OpenCode assets and checksums: succeed as a
  no-op;
- an existing tag at another catalog, mismatched draft metadata, unexpected
  draft assets, or any missing, extra or different asset on an already
  published release: fail.

Rerun the failed push workflow while its request commit is still current
`origin/main`. If `main` has moved, open a new request-only PR with the same
channel/catalog/RC values and a new `requestId`. This preserves a reviewable
retry without changing or reusing immutable release content.

## Rollback and containment

Do not rewrite a bad release. Stop adoption and:

1. Revert each managed consumer's marketplace `ref` to the last reviewed tag.
2. For a personal install on the floating auto-update channel, either disable
   the plugin while investigating or pin the marketplace to the previous tag,
   which intentionally disables automatic advancement. Uninstall and reinstall
   `grillmester` from that tag before starting a new session.
3. Publish a new version containing the correction. Catalog version reuse is
   rejected, including reuse of an older historical version.

For an OpenCode installation, run `rollback` with the manager from the
checksum-verified, extracted release bundle after stopping the active session.
It re-verifies `active` and `previous` before atomically swapping them; do not
recover by editing state, copying a target from a checkout, or replacing a
published asset.

Normal recovery is roll-forward. Any temporary ruleset enforcement change must
be authorized by a repository administrator, recorded in the incident, returned
to `active` immediately, and followed by fresh readback.

If the publisher is wedged by a malformed `marketplace` tip, do not force-push
or edit the branch manually. Disable release publication, preserve the bad SHA
as incident evidence, fix the publisher on `main`, and use a reviewed recovery
through the protected automation identity. Re-enable it only after generator,
validator, remote install smoke, and history/version guards pass.

Record the catalog SHA, source SHA, OpenCode asset SHA-256, tags, consumer refs,
request ID, and recovery actions in the incident. Repinning or manager rollback
does not make an already-started agent session forget loaded content; restart
the affected Copilot or OpenCode session.
