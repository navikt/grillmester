# Change later, rollback and backups

## What apply does

Apply checks schema and a fresh digest under `BEGIN IMMEDIATE`, backs up,
merges policies and enables sandbox for valid projects. Failed DB writes roll
back. After commit, only planned, still-empty, non-symlink placeholders are
removed; cleanup failures warn without undoing policy.

## Change later

- Rerun plan/apply to change masking or use Settings → Projects → Sandbox.
  Default apply re-enables valid projects; profile apply preserves their toggle.
- `rollback --from <backup>` previews; confirm with the same command plus
  `--confirm <digest>`. It restores shared project policies/toggles and **only
  our instructions block**, preserving current user text. Malformed current/
  backup markers skip that rollback project with a warning. Never replace DB.
  A fresh backup makes rollback reversible; repeat the new-session verify gate.

## Backups

- Apply/rollback retain ten matching DB backups in the denied 0700
  `~/.copilot/app-sandbox-setup-backups` directory (files 0600).
- `--move-backups` confirms loose-copy moves into it after commit; no symlink
  moves, overwrite or deletion. Failures warn without undoing DB changes.
