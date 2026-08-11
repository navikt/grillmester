# Provenance

This repository owns the operative Grillmester plugin content. The sources below are recorded for attribution and review history; they are not runtime dependencies and do not create a synchronization relationship.

| Local content | Reviewed source | Adaptation |
| --- | --- | --- |
| `agents/grillmester.agent.md` | `navikt/syfo-budstikka@dd0976ea69d92b6796ee09829ea4e08edc313e14`, `.github/agents/grillmester.agent.md` | Kept the end-to-end phase loop, risk model and one-writer boundary; removed consumer-specific routing and reduced the first slice to three namespaced agents and three skills. |
| `agents/grillmester-implementer.agent.md` | `navikt/syfo-budstikka@dd0976ea69d92b6796ee09829ea4e08edc313e14`, `.github/agents/kokk.agent.md` | Renamed the internal writer, completed the typed brief and side-effect contract, and retained the no-delivery boundary. |
| `agents/grillmester-reviewer.agent.md` | `navikt/syfo-budstikka@dd0976ea69d92b6796ee09829ea4e08edc313e14`, `.github/agents/grill-inspektor.agent.md` | Renamed the read-only reviewer, made Grillmester the explicit evidence producer, and routed security red signals through the portable security skill. |
| `skills/grillmester-grilling/SKILL.md` | `navikt/syfo-budstikka@dd0976ea69d92b6796ee09829ea4e08edc313e14`, `.github/skills/grilling/SKILL.md`; originally adapted from `mattpocock/skills@2ab958093e83e0ec752e6c1c5932da465bf23e0c` | Namespaced and tightened around fact discovery, one decision at a time, recommendations, consequences, and explicit shared understanding. |
| `skills/grillmester-review/SKILL.md` | `navikt/syfo-budstikka@dd0976ea69d92b6796ee09829ea4e08edc313e14`, `.github/skills/review/SKILL.md` | Extracted the portable six-axis diff review and removed Budstikka, Ktor, Gradle, local documentation, and delivery assumptions. |
| `skills/grillmester-security-review/` | `navikt/syfo-budstikka@dd0976ea69d92b6796ee09829ea4e08edc313e14`, `.github/skills/security-review/` | Reworked into a stack-neutral security workflow with conditionally disclosed NAV and NAIS guidance; removed service state, paths, package names, and unsupported universal policy claims. |

The Budstikka source records `navikt/hovmester@48483bf32c2b6f89c31e7d50e25b5fe6fac45ca2` as lineage for its reusable agent contracts. Grillmester preserves that history without treating Hovmester as an upstream distribution channel.

Material adapted from `mattpocock/skills` remains subject to its MIT license. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

When imported material changes, update this file in the same change with the exact source path and full reviewed revision. Advancing a revision means reviewing the concrete upstream diff; changing only the recorded pin is insufficient.
