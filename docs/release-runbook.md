# Release and rollback runbook

Grillmester has an immutable, two-step release identity:

1. `v<manifest-semver>` points to a **catalog-only commit** reachable from the
   `marketplace` branch.
2. Its only package is `grillmester` from `plugin`. The catalog's `source.sha`
   points to the exact source commit reachable from `main`.

The tag identifies the catalog, not the source tree. GitHub's automatically
generated source archive for the release therefore contains only
`.github/plugin/marketplace.json`; it is not an installation artifact. Install
the Copilot plugin through the Grillmester marketplace. The same GitHub Release
also attaches a deterministic terminal bundle and detached `.sha256`. Verify
the checksum and extract the archive to install it. OpenCode, Copilot CLI and
cplt remain separately installed system clients resolved from `PATH`.
Never move, replace, delete, or force-update a release tag or replace an
existing release asset. Each release has exactly two maintained assets: the
terminal bundle and its detached checksum.

## Workflow and trust boundary

One workflow, **Release** (`.github/workflows/release.yml`), publishes both the
floating catalog and the immutable release. It runs when a merge to `main`
changes the version in `plugin/plugin.json`, and it can be dispatched from
`main` to resume or retry. Its stages keep the previous trust boundary:

- **Plan** is read-only. It requires the run to be current `origin/main` and
  releases nothing when `v<version>` is already a published release. Any
  release lookup failure other than 404 fails closed. A missing or draft
  release is (re)published, so any later run resumes an interrupted version.
  When the floating `marketplace` tip already carries the current version, the
  run resumes that catalog's exact source; otherwise it releases current
  `main`.
- **Catalog validation** binds the planned source SHA, regenerates and seals the
  one-package catalog before any selected-source tooling runs, and executes the
  selected source's own tooling and tests only in that read-only job. Copilot
  compatibility runs trusted smoke tooling from `main` and installs the sealed
  catalog and the source payload from a worktree with the supported minimum
  Copilot CLI 1.0.79, which must advertise the complete local-run flag surface in
  `--help` without authentication or a model request. The native macOS matrix
  runs on Apple Silicon and hosted Intel. It verifies the exact OpenCode,
  Copilot CLI and cplt release-test artifacts before their first execution,
  runs the native and cplt runtime smokes, and launches all four local-model
  combinations (OpenCode/Copilot CLI × focused/full) through cplt. Copilot
  scenarios force normal delegation to Grill-inspektøren and require the exact
  loopback model in the primary, subagent and return requests. Those exact
  versions are reproducible release-test input, not local-launcher runtime
  pins. The same matrix also starts a real installed Copilot CLI through the
  installed launcher and cplt with OpenCode excluded from `PATH`, using
  `--help` without a model call. These gates run once per release; the
  release stage reuses them for the same source SHA.
- **Catalog publication** is a one-step write job on a fresh runner. It executes
  no selected-source code, revalidates the sealed bytes, creates a
  catalog-only child of the current `marketplace` tip, and performs a normal
  fast-forward push. An identical tip is an idempotent no-op. A following
  read-only smoke installs from the actual floating `marketplace` ref. Users on
  the floating channel receive the version from this point, before the
  immutable release is sealed.
- **Release sealing** requires the published catalog commit to bind the planned
  source, validates the complete chain and stages the exact catalog bytes and
  source-pinned payload in an isolated local smoke. It builds the terminal
  bundle twice, requires byte identity, verifies `DISTRIBUTION-MANIFEST.json`,
  and seals the exact `tar.gz`, detached checksum and release notes. A separate
  read-only job retrieves the exact immutable artifact ID and uses fixed
  workflow-owned code to match every archive file, mode, manifest entry, and
  canonical archive property to immutable Git blobs at the selected source SHA.

Catalog publication enters the main-restricted `grillmester-release`
deployment and secret boundary automatically once the catalog gates pass.
Release publication enters it again only after sealing and asset verification
also succeed, and it re-checks the sealed source and catalog against the plan
and the published catalog commit, independently of the job that ran
selected-source code. The two asset files cross that boundary in one immutable Actions
artifact; only its exact artifact ID, server digest, file digests, sizes and
names cross as scalar outputs. Its write-capable job contains two fixed inline
steps with no checkout, action, package install, or repository-script
execution. The first uses the environment's Administration:read token only to
require that immutable GitHub Releases are enabled. The second alone receives
the ordinary contents-write token, fetches only the sealed artifact ID, binds it
back to the same workflow run and digest, requires exactly the two expected
files, and may therefore only publish the already source-bound sealed bytes
without executing selected-source code. It finally requires the published
release object to report `immutable: true`. After publication, a read-only job
verifies the tag target, installs from the actual remote `v<version>`
marketplace ref, downloads both assets, checksum-verifies the bundle, and
exercises the terminal bundle's install contract.

The source reachability control relies on the current linear/squash `main`
history. If merge commits are enabled, strengthen it to require first-parent
membership. Every stage requires its run to still be current `origin/main`; if
`main` advances during a release, the run fails closed before its next write and
a dispatch from current `main` resumes it.

### Terminal asset contract

The asset's `DISTRIBUTION-MANIFEST.json` must identify the outer distribution
as `grillmester-terminal-v1` and bind the selected source SHA, the exact client
test baseline under `releaseTest`, the inner target manifests (including the
`opencode-v1` target), the canonical Copilot full-payload manifest, the common
launcher, and the complete distribution inventory. Standard and local launch
accept OpenCode 1.x from the supported minimum, Copilot CLI 1.x from its
minimum and newer dated cplt releases. `scripts/release_test_baseline.py` is the single
executable source contract for exact release-test versions, URLs, sizes,
archive rosters and digests; it is not a shipped client or runtime pin. Passing
this release gate proves the packaged surface and deterministic test contract,
not quality parity for an arbitrary local or cloud model.

The npm integrity and GitHub Release asset digests committed in that executable
baseline bind the bytes accepted by the gate. They are not a separately
verified maintainer signature or artifact attestation. The test-baseline cplt
release is marked mutable upstream, so any later byte replacement fails against
the committed archive and executable digests. Linux artifacts remain test
inputs only; they do not create a Linux support claim for the macOS release.

Protected `main`, the version-bump trigger, rulesets, and the environment
boundary are process and accidental-misdispatch controls. A normal repository
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

- Protect `main`. Changes reach it only through pull requests, and merging a
  pull request that bumps `plugin/plugin.json` is the release decision. An
  independent Grill-inspektør review is recommended before that merge.
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
  `main`, and do not configure required reviewers or enable
  prevent-self-review. Keep administrator bypass disabled. Store a dedicated
  fine-grained credential named `IMMUTABLE_RELEASES_ADMIN_READ_TOKEN` in that
  environment with Administration **read-only** access to this repository. Do
  not grant it contents write and do not reuse the release publisher token;
  the workflow exposes it only to the read-only immutable-setting preflight.

Merely naming an environment in YAML does not establish this deployment and
secret boundary: GitHub can create an unconfigured environment automatically.
Verify the deployment branch restriction and environment-only secret in GitHub
before the first release. The Release workflow holds the
`publish-grillmester-marketplace` concurrency group so two releases cannot
race.

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

1. During a planned release, confirm that **Release** performs its normal
   fast-forward push to `marketplace`.
2. In the same run, confirm that it creates the new `v<version>` tag and that
   its remote smoke succeeds.
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
`main`, and the environment boundary remain defense-in-depth controls, not proof of
strict writer separation.

## Publish a release

There is one release flow and one channel. A version is just a version: a
strict SemVer prerelease suffix marks the GitHub Release as a prerelease, and a
plain version marks it as the latest stable release. Nothing else distinguishes
them, and no release is promoted from another.

Changes can merge to `main` without being released. To roll them out:

1. In the pull request that should release, run:

   ```bash
   python3 scripts/bump_version.py patch
   ```

   Use `minor`, `major`, or an explicit strict SemVer such as `0.5.0-rc.1`
   instead of `patch` when that fits. Like `semver inc`, a bump of the level a
   prerelease belongs to finalises it (`0.5.0-rc.1` + `minor` is `0.5.0`). Build metadata is not accepted, and a
   version must never be reused for different payload bytes. The script
   updates `plugin/plugin.json` and regenerates every derived target.
2. When the change touches rights-scoped imported content (Designer, Doctor
   Who or a Hovmester-imported skill), the script refuses until the stable
   rights journal is rebound. Rerun it with the pull request that reviews that
   content:

   ```bash
   python3 scripts/bump_version.py patch --rights-review navikt/grillmester#123
   ```

   Each `decisionReference` then retains the underlying rights decision and a
   distinct current-content review in the form `underlying decision: …;
   current-content review: …`. The prior decision alone does not approve a
   changed digest; get a new rights or brand decision when the change is
   outside its source, component, or naming scope.
3. Merge the pull request. **Release** starts automatically, publishes the
   catalog to `marketplace`, and publishes the immutable `v<version>` release
   with its terminal bundle and checksum.

The floating `marketplace` branch is also the personal CLI auto-update channel.
It advances when a version bump's catalog gates pass, before the immutable
release is sealed; an ordinary merge without a version bump does not deploy
it. Keep an isolated Copilot home on the previous
version, start a new trusted CLI session after publication, and verify that it
advances without an explicit update command. This is post-deployment evidence
and is separate from the immutable-tag smoke. Use an immutable release tag for
a deliberately staged rollout. Record App and VS Code behavior separately;
neither may be inferred from the CLI result.

The read-only asset verifier checks the archive's bounded gzip/tar structure,
canonical manifest, complete inventory, modes, and file bytes against immutable
Git blobs. The write step then fetches and revalidates the refs again immediately
before it mutates GitHub. It resolves the same sealed artifact ID through the
Actions API, requires the expected workflow-run ID and server digest, and checks
the exact inner bytes and detached checksum again. It creates an annotated tag at
the catalog commit, then stages a draft GitHub Release with `--verify-tag`. Only
an unpublished draft may have the two sealed asset names retried with
`--clobber`; unexpected draft assets fail closed. The step downloads and
byte-verifies both staged assets before publishing the draft (`prerelease` and
`latest=false` for a prerelease). Published assets are never replaced. The
following read-only `release-smoke` job peels the published tag back to the
expected catalog commit, installs from `navikt/grillmester#v<version>`,
byte-verifies the 8-agent/43-skill Copilot payload, downloads the exact
two-asset roster, verifies the detached checksum before safe extraction, and
exercises the launcher's install contract. A failed post-publication smoke
stops promotion and requires a new corrective version; tags and assets are
never replaced.

### Gate the local-model harness

Before a release is called ready for a local-model pilot, both Apple Silicon and
Intel jobs must run the bundled `scripts/smoke_grillmester_local.py` with
`--require-binaries`. The gate uses checksum-verified cplt, OpenCode and
Copilot CLI binaries, one deterministic loopback provider and no GitHub Copilot
cloud model. It fails if the wrong focused/full payload loads, the consumer
repository changes, a credential or caller-PATH canary leaks, any of Copilot's
three delegation requests uses another model ID, or the fake-`gh` matrix cannot
allow a current-repository issue while blocking cross-repository, destructive
and token-extraction commands. The fake CLI never contacts GitHub.

The protocol smoke is not model quality. Before recommending a release for
local-model use, run that immutable release against at least one actually
permitted local model in both clients. Record the model artifact/revision, quantization, server version,
machine, context limit, focused/full input tokens, tool calls, delegation,
output quality and that Copilot reports zero premium requests. Use an empty,
disposable consumer repository and no cloud model. Passing a Qwen pilot does
not extend the support claim to another model or quantization.

## Idempotency and interrupted publication

The publisher never moves an existing tag:

- no tag and no release: create both;
- correct tag but no release: keep the tag, create a draft, stage and verify the
  two assets, then publish;
- correct tag and an exact or partially uploaded draft containing no unexpected
  asset names: retry the two sealed names, byte-verify them, then publish;
- exact tag, release metadata, bundle and checksum: succeed as a no-op;
- an existing tag at another catalog, mismatched draft metadata, unexpected
  draft assets, or any missing, extra or different asset on an already
  published release: fail.

Rerun the failed jobs while the run's commit is still current `origin/main`.
If `main` has moved, the next run resumes the version: a push that changes
`plugin/plugin.json`, or a dispatch of **Release** from current `main`. When the
floating `marketplace` tip already carries that version, the run resumes the
published catalog and its exact source; the catalog step is then a no-op and
the release step continues from the existing tag or draft. A later version
bump supersedes an interrupted one; the interrupted version then has a catalog
commit but no immutable release.

## Rollback and containment

Do not rewrite a bad release. Stop adoption and:

1. Revert each managed consumer's marketplace `ref` to the last reviewed tag.
2. For a personal install on the floating auto-update channel, either disable
   the plugin while investigating or pin the marketplace to the previous tag,
   which intentionally disables automatic advancement. Uninstall and reinstall
   `grillmester` from that tag before starting a new session.
3. Publish a new version containing the correction. Catalog version reuse is
   rejected, including reuse of an older historical version.

The PATH-client launcher does not manage client installation or rollback.
Stop the active session and recover Grillmester, OpenCode or cplt through its
own installation channel. Do not recover by copying a target from a checkout or
replacing a published asset.

Normal recovery is roll-forward. Any temporary ruleset enforcement change must
be authorized by a repository administrator, recorded in the incident, returned
to `active` immediately, and followed by fresh readback.

If the publisher is wedged by a malformed `marketplace` tip, do not force-push
or edit the branch manually. Disable release publication, preserve the bad SHA
as incident evidence, fix the publisher on `main`, and use a reviewed recovery
through the protected automation identity. Re-enable it only after generator,
validator, remote install smoke, and history/version guards pass.

Record the catalog SHA, source SHA, test artifact SHA-256, tags, consumer refs,
workflow run ID, and recovery actions in the incident. Repinning or reinstalling
does not make an already-started agent session forget loaded content; restart
the affected Copilot or OpenCode session.
