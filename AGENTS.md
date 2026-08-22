# Repository contract

This repository owns the portable Grillmester Copilot plugin in `plugin/`
and the generated native OpenCode 1 target in `targets/opencode-v1/`: seven
agents and 42 skills, plus 42 explicit OpenCode commands. The Copilot source
and target-neutral prompt bodies remain canonical; regenerate the OpenCode
projection through `scripts/generate_opencode.py` instead of editing it by
hand. Keep both targets deterministic and independent of any single consumer
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
  decision. Record a qualifying decision as a sequentially numbered ADR in
  `docs/adr/`; use `CONTEXT.md` for canonical project language rather than
  implementation detail.
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
python3 scripts/generate_opencode.py --check
python3 scripts/validate.py
python3 -m unittest discover -s tests -v
node --check plugin/skills/grillmester-design-prototype/scripts/server.js
node --check plugin/skills/grillmester-design-prototype/scripts/helper.js
node --test plugin/skills/grillmester-design-prototype/tests/server.test.js
python3 scripts/smoke_plugin_install.py
python3 scripts/smoke_opencode.py --require-binary
python3 scripts/smoke_opencode_runtime.py --require-binary --cplt cplt
```

The install smoke test must use a disposable, isolated Copilot home. For live
client behavior, use Nav's normal `cplt` setup in an empty, disposable test
repository, pass Copilot's `--plugin-dir plugin` through according to the
current `cplt` documentation, and select the agent with `/agent`.
Never use a consumer repository as a write target for a smoke test.
The OpenCode smoke test must likewise use its disposable consumer repository,
isolated home/config directories, and exactly OpenCode `1.18.20`. Every
cplt-backed profile is release-gated to exactly cplt
`2026.08.17-062831-1008a92`; the runtime smoke must exercise that wrapper and
use only its deterministic loopback provider. It must not contact a real model
or reuse an ambient provider credential. Build release bundles only through
the deterministic bundle builder, and publish the resulting `tar.gz` together
with its detached SHA-256.
