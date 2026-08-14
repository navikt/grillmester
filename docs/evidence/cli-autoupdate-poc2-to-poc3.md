# Copilot CLI auto-update evidence: `poc.2` to `poc.3`

Observed on 2026-08-13 with Copilot CLI 1.0.79 in a trusted local session.
This is sanitized POC evidence, not a guarantee for other clients.

## Setup

- User settings registered `navikt/grillmester` at the floating `marketplace`
  ref with `autoUpdate: true`.
- `enabledPlugins` contained `grillmester@grillmester`.
- The starting installed version was `0.3.0-poc.2`.
- The source catalog commit was
  `c2868047064db0dafdfca54c2bd83a934d9cd546`, whose payload was pinned to source
  commit `eb011c7a01e979b1887938a87c82b8cee95010ce`.

## Observation

After the marketplace advanced and a new Copilot session started, `copilot
plugin list` reported `grillmester@grillmester v0.3.0-poc.3`. Neither `copilot
plugin marketplace update` nor `copilot plugin update` was run between the
baseline and the new session. Catalog commit
`0243e95b646a6815a00204b0006eb77cf91c5136` pinned that version to source commit
`bcf52b87f76fa2e0142b94dee0329c3c64d6ec3a`.

No credentials, user-home contents or consumer-repository contents are retained
here. The Grillmester catalog and source identifiers above are retained as the
minimum reproducibility evidence. The observation proves the tested CLI path
only. Copilot app, cloud agent and VS Code update behavior remain separate
client gates.
