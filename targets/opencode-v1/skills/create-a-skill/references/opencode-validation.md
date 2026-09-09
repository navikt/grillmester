# OpenCode v1 Skill Validation

Load this checklist immediately before validating a created, revised, or
diagnosed skill. Work from a disposable repository or copied config directory
when OpenCode may bootstrap provider or plugin dependencies.

## Structure

- Confirm `SKILL.md` is uppercase and lives one directory below a supported
  `skills/` root.
- Parse frontmatter and verify `name` matches the directory, `description` is
  non-empty, and no unsupported client-specific invocation key is relied on.
- Check relative Markdown links, bundled script permissions, duplicate
  case-folded paths, callers, and any generated target freshness gate.
- If a slash wrapper exists, confirm its filename matches the stable skill ID,
  its body loads that exact ID with the `skill` tool, and it forwards
  `$ARGUMENTS`.
- Inspect ordered `permission.skill` maps. The broad rule must precede narrower
  `ask` or `deny` patterns because the last matching pattern wins.

## Runtime discovery and behavior

Use the installed OpenCode v1 client and its current official CLI contract.
Do not invent an undocumented listing command. In an isolated session:

1. Start OpenCode with the intended config directory and a harmless temporary
   project.
2. Confirm the skill appears in the runtime's available-skill surface or can be
   loaded by its exact name.
3. Invoke the slash wrapper once with inert arguments when one exists.
4. For model-reachable behavior, test one positive and one close-negative
   prompt without putting the expected answer in either prompt.
5. Confirm `ask` and `deny` rules behave as configured; auto mode must not
   override an explicit deny.

Record the client version, config path, agent, model identity, prompt, observed
tool request, result, and exit status. A discovery check proves loading, not
the quality of every skill branch.

Any test that writes external state, deploys, migrates, sends messages, or can
destroy data needs the same explicit authority as ordinary product work.
