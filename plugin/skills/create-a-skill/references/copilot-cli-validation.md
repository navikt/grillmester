# Copilot Client Validation

Load this checklist immediately before validating a created, revised, or
diagnosed skill. Use the intended client's branch; when both app and CLI are
targets, keep their evidence separate. Do not require a second client merely
to complete a task scoped to one.

## Shared structure

Check frontmatter, relative Markdown links, executable permissions for scripts,
and direct callers affected by a changed name or invocation boundary. Confirm
the expected source and revision so a shadowing installed copy cannot stand in
for the edited skill. Report unrelated pre-existing parser errors separately.

## App discovery

Use a fresh app session in a disposable repository with the intended skill
source enabled. Inspect the actual available skill catalog or picker and the
active agent's access to it. Confirm the visible skill comes from the expected
source where the app exposes that evidence. If the app cannot expose source or
invocation evidence, record that limitation rather than treating a plausible
answer as proof of skill selection.

Use the app's supported controls. Do not change global approval settings or
install another integration just to make a validation run pass. An unavailable
app leaves app behavior unverified; continue useful structural checks.

## CLI discovery

Run from the target repository root using the installed client's supported
commands. Where available:

```sh
copilot -C "$PWD" skill list --json
```

Confirm that the target skill parses, is enabled, and comes from the expected
project source. The listing proves CLI discovery, not invocation behavior or
app discovery.

## Invocation behavior

Use a fresh session in the intended client and a temporary fixture, isolated
test repository, dry run, or mock. For autonomous-selection cases, use natural
task prompts without naming the expected skill. Keep the expected answer,
suspected defect, and planned fix out of every test prompt.

- **Manual-only** — verify picker visibility, no autonomous selection, and one
  safe explicit slash execution per distinct branch.
- **Model-only** — verify picker absence, positive and close-negative
  autonomous selection, and one safe representative execution per branch.
- **Both** — verify picker visibility, explicit slash invocation, positive and
  close-negative autonomous selection, and one safe representative execution
  per branch.

A test that writes external state, deploys, migrates, sends messages, or can
destroy data needs the same explicit authority as ordinary product work;
reuse authority already granted for the same bounded action and target.

Record the client and version, skill source or unresolved source limitation,
prompt, observed invocation evidence, resulting action and any unnecessary
questions or scope expansion. Separate structural validity, discovery,
explicit invocation and autonomous selection. A forced load or deterministic
mock can verify a contract without proving natural selection. Report each
unexercised client or behavior as unverified.
