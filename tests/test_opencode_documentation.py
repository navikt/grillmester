from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class OpenCodeDocumentationContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.readme = (ROOT / "README.md").read_text(encoding="utf-8")
        cls.guide = (ROOT / "docs/opencode.md").read_text(encoding="utf-8")
        cls.installation = (ROOT / "docs/installation.md").read_text(
            encoding="utf-8"
        )
        cls.local_models = (ROOT / "docs/local-models.md").read_text(
            encoding="utf-8"
        )
        cls.trust = (ROOT / "docs/trust-and-client-support.md").read_text(
            encoding="utf-8"
        )
        cls.context = (ROOT / "CONTEXT.md").read_text(encoding="utf-8")
        cls.development = (ROOT / "docs/development.md").read_text(
            encoding="utf-8"
        )
        cls.bundle_adr = (
            ROOT / "docs/adr/0002-install-and-launch-opencode-bundles.md"
        ).read_text(encoding="utf-8")
        cls.target_adr = (
            ROOT / "docs/adr/0001-native-opencode-v1-target.md"
        ).read_text(encoding="utf-8")

    def test_domain_documentation_follows_the_repository_convention(self) -> None:
        self.assertFalse((ROOT / "docs/decisions").exists())
        self.assertIn("**Native cplt-flyt**", self.context)
        self.assertIn("**Lifecycle-manager**", self.context)
        self.assertIn("**`local-only`**", self.context)
        self.assertIn("[CONTEXT.md](../CONTEXT.md)", self.development)
        self.assertIn("[`docs/adr/`](adr/)", self.development)
        for adr in (self.target_adr, self.bundle_adr):
            with self.subTest(title=adr.splitlines()[5]):
                self.assertTrue(adr.startswith("---\nstatus: accepted\ndate: "))

    def test_runtime_prerequisites_include_python_311(self) -> None:
        for name, document in (
            ("OpenCode guide", self.guide),
            ("installation guide", self.installation),
        ):
            with self.subTest(document=name):
                self.assertIn("Python `3.11`", document)

    def test_opencode_only_setup_does_not_run_cplt_global_doctor(self) -> None:
        normalized = " ".join(self.guide.split())

        self.assertNotIn("\ncplt doctor\n", self.guide)
        self.assertIn("prober den alle installerte agenter", normalized)
        self.assertIn("ikke en nødvendig OpenCode-sjekk", normalized)
        self.assertIn("kan kjøre `copilot --version`", normalized)

    def test_local_profile_is_not_documented_as_an_egress_guarantee(self) -> None:
        self.assertIn("`local` er altså en lokal-kapabel profil", self.guide)
        self.assertIn("opencode.ai", self.guide)
        self.assertIn(
            "binder provider/base-URL/modell-ID", " ".join(self.local_models.split())
        )

    def test_cloud_profile_documents_intent_and_domain_suffix_semantics(self) -> None:
        self.assertIn("manageren attesterer ikke at\nmodellvektene", self.guide)
        self.assertIn("samme hostname eller et subdomene", self.guide)
        self.assertIn("smaleste faktiske", self.installation)
        self.assertIn("direkte any-host-\nkernelregel", self.guide)
        self.assertIn("åpner direkte\negress til alle", self.installation)

    def test_local_only_names_platform_and_provider_boundaries(self) -> None:
        guide = " ".join(self.guide.split())
        for marker in (
            "full forced-proxy-håndheving på macOS",
            "Launcheren skal derfor feile lukket for `local-only` på Linux",
            "providerprosessen som lytter på localhost",
            "kjører utenfor cplt-sandboxen",
            "Seatbelts `localhost`-selector",
            "eksterne maskiner på samme port klassifiseres som blokkert",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, guide)
        self.assertIn("står også i blocklisten", guide)
        self.assertIn("både allow- og blocklisten", self.local_models)

    def test_cplt_launch_documents_the_fixed_audited_home(self) -> None:
        for name, document in (
            ("OpenCode guide", self.guide),
            ("bundle ADR", self.bundle_adr),
        ):
            with self.subTest(document=name):
                self.assertIn(
                    "~/.local/share/grillmester/opencode", document
                )
        self.assertIn("custom manager-home kan ikke velges\nvia `XDG_DATA_HOME`", self.guide)
        self.assertIn("ikke for en cplt-basert launch", self.bundle_adr)

    def test_docs_distinguish_native_cplt_from_lifecycle_hardening(self) -> None:
        self.assertIn("cplt støtter allerede OpenCode direkte", self.guide)
        self.assertIn("Ingen custom wrapper er nødvendig", self.guide)
        self.assertIn("manageren er valgfri hardening", self.guide)
        self.assertIn("beholder bare kompatibilitetssikre", self.guide)
        self.assertIn("`sandbox.inherit_env`", self.guide)
        self.assertIn(
            "les cplts launchoppsummering", " ".join(self.guide.split())
        )
        self.assertIn("ordinær `cplt --agent opencode`", self.guide)
        self.assertIn("Ekstra filesystem- eller socket-grants", self.guide)
        self.assertIn("peker manageren `CPLT_CONFIG`", self.bundle_adr)
        target_adr = " ".join(self.target_adr.split())
        bundle_adr = " ".join(self.bundle_adr.split())
        self.assertIn(
            "Native cplt binder det utpakkede targetet direkte", target_adr
        )
        self.assertIn(
            "bare brukere som velger high-assurance-livssyklusen", target_adr
        )
        self.assertIn("Native unmanaged cplt kan fortsatt binde", bundle_adr)
        self.assertIn("påstår ikke managerens lifecycle-", bundle_adr)

    def test_opencode_guide_starts_with_native_cplt_quick_start(self) -> None:
        self.assertLess(
            self.guide.index("## Native cplt: kom raskt i gang"),
            self.guide.index("## Installer eksakte klienter"),
        )
        quick_start = self.guide.split(
            "## Native cplt: kom raskt i gang", 1
        )[1].split("## Installer eksakte klienter", 1)[0]
        normalized = " ".join(quick_start.split())

        self.assertIn("cplt støtter OpenCode out of the box", normalized)
        self.assertIn("Grillmester legger bare til én config-dir-binding", normalized)

    def test_native_quick_start_covers_unmanaged_local_and_cloud(self) -> None:
        quick_start = self.guide.split(
            "## Native cplt: kom raskt i gang", 1
        )[1].split("## Installer eksakte klienter", 1)[0]
        normalized = " ".join(quick_start.split())

        self.assertIn("### Lokal modell på macOS", quick_start)
        self.assertIn("--allow-localhost 1234", quick_start)
        self.assertIn("port `8080`", normalized)
        self.assertIn("### Cloud-provider", quick_start)
        self.assertGreaterEqual(
            quick_start.count('OPENCODE_CONFIG_DIR="$CONFIG_DIR"'), 2
        )
        self.assertGreaterEqual(
            quick_start.count("--pass-env OPENCODE_CONFIG_DIR"), 2
        )
        self.assertIn("--pass-env MODEL_PROVIDER_API_KEY", quick_start)
        self.assertIn("HTTPS-port `443` er standard", normalized)
        self.assertIn(
            "managerpolicy eller en eksplisitt, custom cplt-proxypolicy",
            normalized,
        )

    def test_native_copilot_provider_documents_cplt_allowlist_composition(self) -> None:
        quick_start = self.guide.split(
            "## Native cplt: kom raskt i gang", 1
        )[1].split("## Installer eksakte klienter", 1)[0]
        normalized = " ".join(quick_start.split())

        self.assertIn("`standard`-profil", normalized)
        self.assertIn("`--preset strict`", quick_start)
        self.assertIn("`--default-allowlist`", quick_start)
        self.assertIn("`proxy.default_allowlist=true`", quick_start)
        self.assertIn("--allowed-domains", quick_start)
        for domain in (
            "githubcopilot.com",
            "api.github.com",
            "github.com",
            "copilot-proxy.githubusercontent.com",
            "actions.githubusercontent.com",
            "default.exp2.cds.s9ch.io",
        ):
            with self.subTest(domain=domain):
                self.assertIn(domain, quick_start)
        self.assertIn("Ikke bruk\n`--allow-all-domains`", quick_start)

    def test_readme_has_complete_client_journeys_before_optional_hardening(self) -> None:
        self.assertLessEqual(len(self.readme.splitlines()), 110)
        self.assertLess(
            self.readme.index("### GitHub Copilot"),
            self.readme.index("### OpenCode via cplt"),
        )
        section = self.readme.split("### OpenCode via cplt", 1)[1].split(
            "## Velg agent", 1
        )[0]
        normalized = " ".join(section.split())

        journey_markers = (
            "**Forutsetninger:**",
            "**Hent Grillmester:**",
            "**Velg modell:**",
            "**Start med GitHub Copilot-provider:**",
        )
        positions = [normalized.index(marker) for marker in journey_markers]
        self.assertEqual(sorted(positions), positions)
        self.assertLess(
            normalized.index("cplt --agent opencode"),
            normalized.index("lifecycle-flyten"),
        )
        for marker in (
            "docs/opencode.md#installer-eksakte-klienter",
            "docs/opencode.md#hent-og-verifiser-en-grillmester-bundle",
            "docs/opencode.md#valgfri-lifecycle-manager",
            "OPENCODE_CONFIG_DIR",
            "cplt --agent opencode",
            "cd /path/to/consumer-repo",
            "--allow-read",
            "--pass-env OPENCODE_CONFIG_DIR",
            "docs/opencode.md#native-cplt-kom-raskt-i-gang",
            "port- eller credential-tilgangen cplt trenger",
            "ikke nødvendig for vanlig cplt-bruk",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, normalized)

    def test_installation_guide_links_native_quick_start_before_manager(self) -> None:
        introduction = self.installation.split("## Innhold", 1)[0]
        normalized = " ".join(introduction.split())

        self.assertIn("cplt støtter OpenCode direkte out of the box", normalized)
        self.assertIn(
            "opencode.md#native-cplt-kom-raskt-i-gang", introduction
        )
        self.assertLess(
            self.installation.index("opencode.md#native-cplt-kom-raskt-i-gang"),
            self.installation.index("scripts/manage_opencode.py install"),
        )
        self.assertLess(
            self.installation.index("cplt --agent opencode"),
            self.installation.index("### Valgfri high-assurance manager"),
        )

    def test_local_model_guide_leads_with_native_cplt_before_manager(self) -> None:
        section = self.local_models.split(
            "## Koble OpenCode til den lokale serveren", 1
        )[1].split("## Hybrid:", 1)[0]
        self.assertLess(
            section.index("cplt --agent opencode"),
            section.index("scripts/manage_opencode.py launch"),
        )
        self.assertIn("ingen lifecycle-manager eller nav-pilot-agent", section)

    def test_managed_docs_do_not_claim_normal_project_config_merging(self) -> None:
        managed = self.guide.split("## Hva launcheren faktisk gjør", 1)[1].split(
            "## Direkte OpenCode", 1
        )[0]
        normalized = " ".join(managed.split())

        self.assertIn("`OPENCODE_DISABLE_PROJECT_CONFIG=true`", normalized)
        self.assertIn("fingerprintede project-instructions", normalized)
        self.assertIn(
            "auditerte permissionregler med `ask`/`deny`", normalized
        )
        self.assertIn("Den minimale unmanaged cplt-flyten", normalized)
        self.assertNotIn(
            "merger Grillmester-agenter, commands og skills etter globale og "
            "prosjektlokale configkilder",
            normalized,
        )

    def test_nested_dynamic_instruction_limit_is_explicit(self) -> None:
        normalized = " ".join(self.guide.split())
        self.assertIn("kopierer de eksakte byteverdiene", normalized)
        self.assertIn("private config-stagen", normalized)
        self.assertIn("`0444`-filene", normalized)
        self.assertIn("nestet `AGENTS.md` eller `CONTEXT.md`", normalized)
        self.assertIn("ikke en påstand om eksklusiv promptkilde", normalized)

    def test_managed_threat_boundary_names_stock_client_live_read_gaps(self) -> None:
        guide = " ".join(self.guide.split())
        installation = " ".join(self.installation.split())
        adr = " ".join(self.bundle_adr.split())
        for marker in (
            "core V2",
            "restriction-only",
            "disposable preflight-project",
            "`OPENCODE_TEST_HOME`",
            "same-UID",
            "sealed repo-config",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, guide)
        self.assertIn("same-UID", installation)
        self.assertIn("sealed repo-config", installation)
        self.assertIn("same-UID", adr)
        self.assertIn("sealed repo-config", adr)

    def test_native_nav_pilot_coexistence_and_managed_exclusion_are_explicit(self) -> None:
        normalized = " ".join(self.guide.split())
        agents = " ".join(
            (ROOT / "docs/agents-and-skills.md").read_text(encoding="utf-8").split()
        )

        self.assertIn("`EnsureOpenCodeNavContext`", normalized)
        self.assertIn("native/unmanaged cplt", normalized)
        self.assertIn("merge dette med Grillmesters `OPENCODE_CONFIG_DIR`", normalized)
        self.assertIn("bevarte agent-ID-ene", normalized)
        self.assertIn("bruker ikke nav-pilot-eksporten", normalized)
        self.assertIn(
            "arkitekturlinjens proveniens er låst", normalized
        )
        self.assertIn(
            "2d0911b353a91ec9091d252b481acb5777de7059", normalized
        )
        self.assertIn(
            "nyere kompatibilitetsrevisjonen", normalized
        )
        self.assertIn(
            "0c96b8fe7c8167a4dd9fc99e50ea18de08e6bb02", normalized
        )
        self.assertIn("Canonical skill- og command- ID-er", agents)
        self.assertIn("agent-ID-ene er bevart", agents)

    def test_hermetic_modes_and_private_provider_opt_in_are_explicit(self) -> None:
        self.assertIn(
            "--private-provider-domain inference.internal.example", self.guide
        )
        self.assertIn(
            "GRILLMESTER_OPENCODE_PRIVATE_PROVIDER_DOMAINS", self.guide
        )
        self.assertIn("XDG config/data/state/cache erstattes", self.guide)
        self.assertIn("`~/.config/opencode`", self.guide)
        self.assertIn("--private-provider-domain", self.installation)

    def test_runtime_smoke_does_not_overclaim_zero_external_egress(self) -> None:
        self.assertIn("uten ekstern modell", self.trust)
        self.assertIn("ikke kernel-evidens for null ekstern\ntrafikk", self.trust)
        self.assertIn("separat fail-closed nettverksmåling", self.trust)

    def test_managed_cplt_authenticates_and_stages_official_clients(self) -> None:
        guide = " ".join(self.guide.split())
        installation = " ".join(self.installation.split())
        adr = " ".join(self.bundle_adr.split())

        self.assertIn(
            "byte-identisk med en offisiell plattformbinær", guide
        )
        self.assertIn("private `trusted-bin`", guide)
        self.assertIn("opprinnelige OpenCode-binæren startes aldri", guide)
        self.assertIn("OpenCode og cplt byte-identisk", installation)
        self.assertIn("opprinnelige OpenCode-binæren leses, men kjøres ikke", installation)
        self.assertIn("kopierer begge byte-identisk", adr)

        direct = self.guide.split("## Direkte OpenCode", 1)[1].split(
            "## Agenter, commands og forwarding", 1
        )[0]
        self.assertEqual(1, direct.count("scripts/manage_opencode.py launch"))
        self.assertIn("caller-resolverte OpenCode-binæren", direct)
        self.assertIn("trusted-code-opt-out", direct)

    def test_client_bootstrap_trust_boundary_is_explicit(self) -> None:
        for name, document in (
            ("OpenCode guide", self.guide),
            ("installation guide", self.installation),
        ):
            normalized = " ".join(document.split())
            with self.subTest(document=name):
                self.assertIn("`postinstall` kjører `verifyBinary`", normalized)
                self.assertIn("før manageren kan hashe", normalized)
                self.assertIn("Homebrew er en bekvemmelighetsinstallasjon", normalized)
                self.assertIn("eksakte npm-plattformpakken", normalized)
                self.assertIn("eksakte cplt-releaseasseten", normalized)
                self.assertIn("upstream-arkivchecksummen", normalized)
                self.assertIn("binærdigesten før første kjøring", normalized)

        for name, document in (
            ("trust guide", self.trust),
            ("bundle ADR", self.bundle_adr),
        ):
            normalized = " ".join(document.split())
            with self.subTest(document=name):
                self.assertIn("`postinstall`", normalized)
                self.assertIn("`verifyBinary`", normalized)
                self.assertIn("ikke retroaktivt sikre bootstrapen", normalized)

    def test_hardened_profiles_use_only_explicit_safe_provider_models(self) -> None:
        guide = " ".join(self.guide.split())
        trust = " ".join(self.trust.split())

        self.assertIn("`OPENCODE_MODELS_PATH`", guide)
        self.assertIn("manager-eid, read-only tom modellkatalog", guide)
        self.assertIn("`@ai-sdk/openai-compatible`", guide)
        self.assertIn('"baseURL": "https://inference.example.org/v1"', self.guide)
        self.assertIn('"npm": "@ai-sdk/openai-compatible"', self.local_models)
        self.assertIn('"baseURL": "http://127.0.0.1:1234/v1"', self.local_models)
        self.assertIn("--provider-base-url", self.guide)
        self.assertIn("--provider-model", self.guide)
        self.assertIn(
            "positive `limit.context`/ `limit.output`",
            " ".join(self.bundle_adr.split()),
        )
        self.assertIn("Grillmester-tradeoff, ikke et cplt-krav", trust)
        self.assertIn("unmanaged cplt", trust)

    def test_every_managed_provider_launch_binds_base_url_and_model(self) -> None:
        for name, document in (
            ("OpenCode guide", self.guide),
            ("installation guide", self.installation),
            ("local model guide", self.local_models),
        ):
            for block in re.findall(r"```bash\n(.*?)```", document, flags=re.DOTALL):
                if "manage_opencode.py launch" not in block or "--provider-id" not in block:
                    continue
                with self.subTest(document=name, block=block[:80]):
                    self.assertIn("--provider-base-url", block)
                    self.assertIn("--provider-model", block)
        for variable in (
            "GRILLMESTER_OPENCODE_PROVIDER_IDS",
            "GRILLMESTER_OPENCODE_PROVIDER_BASE_URLS",
            "GRILLMESTER_OPENCODE_PROVIDER_MODELS",
            "GRILLMESTER_OPENCODE_AUTH_PROVIDERS",
        ):
            with self.subTest(variable=variable):
                self.assertIn(variable, self.bundle_adr)

    def test_cloud_profile_is_public_only_without_dns_preflight(self) -> None:
        guide = " ".join(self.guide.split())
        installation = " ".join(self.installation.split())
        trust = " ".join(self.trust.split())

        for document in (guide, installation, trust):
            with self.subTest(document=document[:40]):
                self.assertIn("ingen DNS-preflight", document)
        self.assertIn("localhostnavn, IP-litteraler", guide)
        self.assertIn("bruk `hybrid`", guide)
        self.assertIn("tilkoblingstidspunktet", guide)
        self.assertIn("public/private- og loopbackgrensen", installation)
        self.assertIn("Private og interne providernavn hører hjemme i `hybrid`", trust)

    def test_resolved_config_not_overlay_order_is_the_guarantee(self) -> None:
        guide = " ".join(self.guide.split())
        installation = " ".join(self.installation.split())
        trust = " ".join(self.trust.split())

        for document in (guide, installation, trust):
            with self.subTest(document=document[:40]):
                self.assertIn("managed/MDM-config kan merge senere", document)
                self.assertIn("OPENCODE_DISABLE_SHARE=true", document)
        self.assertIn("resolve effektiv config", guide)
        self.assertIn("effektivt resolved config før launch", installation)

    def test_unmanaged_cplt_command_is_minimal_and_manager_is_optional(self) -> None:
        for marker in (
            "CONFIG_DIR=/absolute/path/to/grillmester-opencode-v1/targets/opencode-v1",
            'OPENCODE_CONFIG_DIR="$CONFIG_DIR"',
            'cplt --agent opencode',
            '--allow-read "$CONFIG_DIR"',
            '--pass-env OPENCODE_CONFIG_DIR',
            '-- --agent grillmester',
            "manageren er valgfri hardening",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.guide)

    def test_macos_live_gate_uses_pinned_native_seatbelt_evidence(self) -> None:
        trust = " ".join(self.trust.split())

        self.assertIn("`macos-live-compatibility`", trust)
        self.assertIn("eksakte pinnede Darwin-assetene", trust)
        self.assertIn("rå `/usr/bin/nc`-målinger", trust)
        self.assertIn("Seatbelts `localhost`-selector", trust)
        self.assertIn("dokumentasjonsadresse på samme port", trust)


if __name__ == "__main__":
    unittest.main()
