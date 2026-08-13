# Copilot CLI Validation

Load this checklist immediately before validating a created, revised, or
diagnosed skill. Run commands from the target repository root.

## Structure and discovery

```sh
copilot -C "$PWD" skill list --json
```

Confirm that the target skill parses, is enabled, and comes from the expected
project source. The listing proves discovery, not invocation behavior. Report
unrelated pre-existing parser errors separately.

Also verify relative Markdown links, executable permissions for scripts, and
direct callers affected by a changed name or invocation boundary.

## Invocation behavior

Use a fresh session and a temporary fixture, isolated test repository, dry
run, or mock. Keep the expected answer, suspected defect, and planned fix out
of the prompt.

- **Manual-only** — verify picker visibility, no autonomous selection, and one
  safe explicit slash execution per distinct branch.
- **Model-only** — verify picker absence, positive and close-negative
  autonomous selection, and one safe representative execution per branch.
- **Both** — verify picker visibility, explicit slash invocation, positive and
  close-negative autonomous selection, and one safe representative execution
  per branch.

A test that writes external state, deploys, migrates, sends messages, or can
destroy data needs the same explicit authority as ordinary product work.
