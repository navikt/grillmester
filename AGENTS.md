# Repository contract

This repository owns the portable Grillmester Copilot plugin. Keep the plugin
small, deterministic, and independent of any single consumer repository.

## Content boundaries

- Write portable agent and skill content in English. Answer users in their
  language and preserve established Norwegian domain terms.
- Keep consumer build commands, domain facts, data classifications, language
  mappings, and path-specific rules in consumer repositories.
- Do not distribute `copilot-instructions.md`, `AGENTS.md`, or path-scoped
  instructions as plugin components.
- Do not add a second file-sync lifecycle, managed consumer manifest, install
  hook, MCP server, or executable hook without an explicit architecture
  decision.
- Namespace public component IDs with `grillmester` and remove references to
  legacy Hovmester IDs.

## Verification

Run before publishing a change:

```bash
python3 scripts/validate.py
python3 -m unittest discover -s tests -v
```

For client behavior, mount the plugin with `copilot --plugin-dir .` in an
isolated `COPILOT_HOME`. Never use a consumer repository as a write target for
a smoke test.
