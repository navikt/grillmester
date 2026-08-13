# Repository contract

This repository owns the portable Grillmester Copilot packages: the standard
agent team in `plugin/` and the optional, skills-only NAV add-on in
`plugin-nav/`. Keep both deterministic and independent of any single consumer
repository.

## Content boundaries

- Write portable agent and skill content in English by default. An explicitly
  reviewed role may use Norwegian when its audience and voice require it.
  Answer users in their language and preserve established Norwegian domain
  terms.
- Keep consumer build commands, domain facts, data classifications, language
  mappings, and path-specific rules in consumer repositories.
- Do not distribute `copilot-instructions.md`, `AGENTS.md`, path-scoped
  instructions, PR templates, or issue templates as plugin components.
- Do not add a second file-sync lifecycle, managed consumer manifest, install
  hook, MCP server, or executable hook without an explicit architecture
  decision.
- Preserve the reviewed pilot agent IDs. Canonical runtime skill IDs use the
  `grillmester-` prefix to reduce accidental collisions. A project- or
  user-level component with the same exact ID still wins and can silently
  shadow the plugin component; qualification is not a bypass. Preserve the
  original source ID in provenance and human-facing headings, and remove
  references to obsolete Hovmester runtime IDs.

## Verification

Run before publishing a change:

```bash
python3 scripts/generate_marketplace.py --mode development --check
python3 scripts/validate.py
python3 scripts/validate_evals.py
python3 -m unittest discover -s tests -v
node --check plugin/skills/grillmester-design-prototype/scripts/server.js
node --check plugin/skills/grillmester-design-prototype/scripts/helper.js
node --test plugin/skills/grillmester-design-prototype/tests/server.test.js
python3 scripts/smoke_plugin_install.py
```

The install smoke test must use a disposable, isolated Copilot home. For live
client behavior, mount the standard package with `copilot --experimental
--sandbox --plugin-dir plugin` and optionally add `--plugin-dir plugin-nav`, in
an empty test repository. Confirm the sandbox status and effective policy;
an empty repository is not a sandbox substitute.
Never use a consumer repository as a write target for a smoke test.
