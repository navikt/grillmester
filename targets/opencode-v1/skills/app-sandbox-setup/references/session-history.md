# Shared session history

The standard setup grants readonly access to `~/.copilot/session-state`.
This covers current and future session IDs, including checkpoints the app
may omit from its automatic grants. It deliberately permits cross-project
history reads, not just access to the current conversation. History can
contain confidential material; explain this boundary before confirmation.
Access is not permission to retrieve unrelated history or expose its contents.

## Change only this setting

Use this branch when the user wants history access updated without rerunning
toolchain, network, credential or Docker setup:

```sh
python3 <script> history plan
python3 <script> history apply --confirm <digest>
```

Omitting `--project` targets every configured Copilot project; do that only
when the user requested all projects. Otherwise pass the exact configured
project directory to both commands. Add `--no-session-history` to both
commands to remove only the exact shared grant. Readonly and readwrite entries
that name the same directory by case, trailing slash or symlink count as that
grant. The same opt-out works with normal `plan`, `apply` and `guide`; repeat
it on later setup runs.

Follow the normal plan/confirmation/apply contract. Reuse an explicit approval
for this precise scope only when the generated diff matches it; otherwise
confirm the changed scope. `history apply` preserves sandbox defaults,
credentials, network, Docker, instructions and other path entries. It uses
the existing schema, transaction, digest and protected-backup safeguards.
No history contents are read, directories created, loose backups moved or
placeholder directories removed; the protected backup directory is created on
the first apply that writes. An existing deny is preserved and reported; never
remove it implicitly. Writable history grants are still removed under a deny.
Projects without a sandbox policy are skipped; run normal setup for them first.
Redirected or unreadable history roots are refused; fix the directory or use
`--no-session-history`.

Normal setup includes this default for projects configured later. There is no
new automatic hook: adding a project in the app still requires a setup run.
The app and standalone CLI keep separate policies; this is app configuration,
not an operating-system-wide grant to other applications.

## Verify the actual sandbox

After applying, follow the main skill's sandbox-on/restart procedure. Repeat
the originally denied checkpoint read with the **same tool**, then check that
the current session can still create and remove a disposable artifact in its
own app-provided `files/` directory. Do not modify checkpoints or other
sessions as a write probe.

A saved policy or an unsandboxed read is not runtime proof. If a read or the
app's own artifact write fails, stop at that boundary and inspect only the
relevant filesystem rules with permission; do not change readers to bypass
denial or broaden to `.copilot`. Explicit denials and enterprise restrictions
need their owner's decision.
