# Behavioral review cases

[`cases.json`](cases.json) is a small checklist for reviewing changes to agent
and skill behavior. It records representative prompts together with what
should and should not happen.

These are not automated model evaluations. CI checks only that the JSON is
well formed and that referenced agents and skills still exist. It does not
invoke Copilot, score model output, or claim that behavior has passed.

When a change affects routing or behavior:

1. Run the relevant cases manually in a disposable repository and supported
   client.
2. Record the client, model, version, observed tools and result in the PR.
3. Run cases marked `safety: true` in isolation, with synthetic data and no
   real credentials, personal data, or external write targets.
4. Report an unrun or ambiguous case as unverified, never as passed.

Each `expected` or `forbidden` value has the form `<kind>:<target>`. Agent and
skill targets are checked against the shipped plugin. Response and status
labels are plain review criteria, not hidden oracles.
