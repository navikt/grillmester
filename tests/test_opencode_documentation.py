from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def normalized(text: str) -> str:
    return " ".join(text.split())


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
        cls.release_runbook = (ROOT / "docs/release-runbook.md").read_text(
            encoding="utf-8"
        )
        cls.provenance = (ROOT / "PROVENANCE.md").read_text(encoding="utf-8")
        cls.adrs = {
            number: next((ROOT / "docs/adr").glob(f"{number}-*.md")).read_text(
                encoding="utf-8"
            )
            for number in ("0001", "0002", "0003", "0004", "0005", "0006", "0007")
        }

    def test_domain_documentation_follows_the_repository_convention(self) -> None:
        self.assertFalse((ROOT / "docs/decisions").exists())
        for term in (
            "**Native cplt-flyt**",
            "**Terminal-launcher**",
            "**Launcherpreferanse**",
            "**Systemklient**",
            "**Local-model-launcher**",
        ):
            with self.subTest(term=term):
                self.assertIn(term, self.context)
        for removed_term in (
            "**Lifecycle-manager**",
            "**Runtimeprofil**",
            "**`local-only`**",
        ):
            with self.subTest(removed_term=removed_term):
                self.assertNotIn(removed_term, self.context)

        self.assertIn("[CONTEXT.md](../CONTEXT.md)", self.development)
        self.assertIn("[`docs/adr/`](adr/)", self.development)
        for number in ("0001", "0003", "0004", "0005", "0006", "0007"):
            with self.subTest(adr=number):
                self.assertTrue(
                    self.adrs[number].startswith("---\nstatus: accepted\ndate: ")
                )
        self.assertTrue(
            self.adrs["0002"].startswith(
                "---\nstatus: superseded by ADR-0007\ndate: "
            )
        )
        self.assertIn("0007-remove-the-lifecycle-manager.md", self.adrs["0002"])
        for number in ("0001", "0003"):
            with self.subTest(supersession=number):
                self.assertIn(
                    "0007-remove-the-lifecycle-manager.md", self.adrs[number]
                )

    def test_system_clients_are_user_owned_and_cplt_is_the_only_runtime_boundary(self) -> None:
        decision = normalized(self.adrs["0004"])
        installation = normalized(self.installation)
        guide = normalized(self.guide)
        trust = normalized(self.trust)

        for marker in (
            "OpenCode og Copilot CLI er valgfrie systemklienter",
            "Launcheren resolver `cplt`, `opencode` og `copilot` fra `PATH`",
            "cplt er fortsatt en hard runtimegrense",
            "det finnes ingen direkte eller stille fallback",
            "OpenCode `>=1.18.20,<2`",
            "Copilot CLI `>=1.0.79,<2`",
            "installert Copilot CLI uten OpenCode",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, decision)

        self.assertIn("brukereide systemklienter", installation)
        self.assertIn("formelen installerer, erstatter eller skygger dem aldri", installation)
        self.assertIn("resolver `opencode` fra `PATH`", guide)
        self.assertIn("installerer, erstatter eller skygger aldri klienten", guide)
        self.assertIn(
            "Standardlauncheren bruker OpenCode og Copilot CLI fra brukerens `PATH`",
            trust,
        )
        self.assertIn("cplt eier runtimegrensen", normalized(self.adrs["0007"]))

    def test_exact_artifacts_are_release_test_inputs_not_runtime_pins(self) -> None:
        for name, document in (
            ("installation", self.installation),
            ("local models", self.local_models),
            ("trust", self.trust),
            ("ADR 0006", self.adrs["0006"]),
            ("release runbook", self.release_runbook),
        ):
            value = normalized(document)
            with self.subTest(document=name):
                self.assertIn("OpenCode", value)
                self.assertRegex(value, r"testinput|test input|testmetadata")
                self.assertRegex(value, r"runtimepinn|runtime pin|ikke pinner")

        local_decision = normalized(self.adrs["0006"])
        self.assertIn("OpenCode `>=1.18.20,<2`", local_decision)
        self.assertIn("Copilot CLI `>=1.0.79,<2`", local_decision)
        self.assertIn("skal derfor ikke ha en upstream-watch", local_decision)
        self.assertIn(
            "En kompatibel 1.x-klientoppgradering krever normalt ingen Grillmester-release",
            normalized(self.adrs["0007"]),
        )
        for name, document in (
            ("provenance", self.provenance),
            ("trust", self.trust),
            ("ADR 0007", self.adrs["0007"]),
            ("release runbook", self.release_runbook),
        ):
            with self.subTest(executable_baseline=name):
                self.assertIn("scripts/release_test_baseline.py", document)
                self.assertNotIn("policy/client-artifacts.json", document)
                self.assertNotIn("verify_client_artifact.py", document)

    def test_terminal_bundle_name_matches_the_current_release_contract(self) -> None:
        for name, document in (
            ("provenance", self.provenance),
            ("development", self.development),
            ("OpenCode", self.guide),
            ("release runbook", self.release_runbook),
        ):
            with self.subTest(document=name):
                self.assertIn("grillmester-terminal-", document)
                self.assertNotIn("grillmester-opencode-", document)

    def test_lifecycle_manager_is_removed_from_supported_paths(self) -> None:
        supported_documents = {
            "README": self.readme,
            "OpenCode guide": self.guide,
            "installation": self.installation,
            "local models": self.local_models,
            "trust": self.trust,
            "development": self.development,
            "release runbook": self.release_runbook,
        }
        for name, document in supported_documents.items():
            with self.subTest(document=name):
                self.assertNotIn("scripts/manage_opencode.py", document)
                self.assertNotIn("## Valgfri lifecycle-manager", document)
                self.assertNotIn("### Valgfri high-assurance manager", document)
                self.assertNotIn("--profile local-only", document)
                self.assertNotIn("upstream-client-watch", document)

        removal = normalized(self.adrs["0007"])
        for marker in (
            "Lifecycle-manageren, runtimeprofilene og den private `trusted-bin`-/staging- livssyklusen fjernes",
            "Det finnes ingen Grillmester-eid `local-only`-profil eller `--direct`-bakvei",
            "Kontrakten er ikke en runtimepin, installasjonsmetadata eller en alternativ distribusjon",
            "manageren aldri ble publisert",
            "Ingen migrering eller rollbackmekanisme er nødvendig",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, removal)

        system_clients = normalized(self.adrs["0004"])
        self.assertIn("ADR 0007 fjerner manageren og private klientkopier", system_clients)
        self.assertNotIn("Team med behov for slik binding må velge", system_clients)

    def test_local_mode_is_connected_local_inference(self) -> None:
        local_models = normalized(self.local_models)
        trust = normalized(self.trust)
        decision = normalized(self.adrs["0006"])

        for marker in (
            "Local-flyten har ingen cloudmodell-fallback, men den kan være tilkoblet",
            "Launcheren åpner den valgte localhost-porten og krever cplts forced proxy",
            "Webverktøy og dokumentasjonskilder virker",
            "cplt-config forblir autoritativ",
            "Grillmester åpner ikke alle domener",
            "legger en annen sandbox oppå",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, local_models)

        self.assertIn(
            "web/GitHub følger cplt-policy", normalized(self.readme)
        )
        self.assertIn("Websearch, dokumentasjon og GitHub", trust)
        self.assertIn("lokal inference, ikke offline", normalized(self.guide))
        self.assertIn("ingen offlinegaranti", decision)
        self.assertIn("cplt er eneste runtimeeier", decision)

    def test_local_github_contract_is_explicit_for_both_clients(self) -> None:
        local_models = normalized(self.local_models)
        trust = normalized(self.trust)
        decision = normalized(self.adrs["0006"])

        for document in (local_models, trust, decision):
            with self.subTest(document=document[:60]):
                self.assertIn("`GH_TOKEN`", document)
                self.assertIn("child-", document)
                self.assertIn("myk", document)
                self.assertIn("lese", document)

        self.assertIn(
            "Launcheren skriver ikke tokenet til config, sessionstate eller preview",
            local_models,
        )
        self.assertIn("innebygde GitHub MCP er av", local_models)
        self.assertIn("guarded `gh`", local_models)
        self.assertIn("Git push forblir under Git-guard", local_models)
        self.assertIn("OpenCodes websearch er aktiv", local_models)
        self.assertIn("permission krever godkjenning", local_models)
        self.assertIn("cplt-credentialmediering", trust)
        self.assertIn("rå credentialstore", trust)
        self.assertIn("eksplisitte cplt `--deny-path`", trust)
        self.assertIn("`--no-audit`", trust)
        self.assertIn("parent-side Git-audit", decision)
        for document in (local_models, trust, decision):
            with self.subTest(explicit_github=document[:60]):
                self.assertIn("`--github-access`", document)
                self.assertIn("uten å kjøre `gh`", document)
                self.assertRegex(document, r"persistere")

    def test_opencode_guide_starts_with_the_homebrew_launcher(self) -> None:
        self.assertLess(
            self.guide.index("## Kom i gang"),
            self.guide.index("## Avansert: manuell binding og verifisering"),
        )
        quick_start = self.guide.split("## Kom i gang", 1)[1].split(
            "## Avansert: manuell binding og verifisering", 1
        )[0]
        value = normalized(quick_start)

        self.assertLess(
            value.index("ikke tilgjengelig"),
            value.index("brew install navikt/tap/cplt navikt/tap/grillmester"),
        )
        for marker in (
            "brew install opencode",
            "resolver `opencode` fra `PATH`",
            "grillmester choose",
            "ingen stille fallback til Copilot",
            "starter alltid OpenCode gjennom cplt",
            "### Lokal modell på macOS",
            "grillmester local setup --client opencode",
            "### Cloud-provider",
            "--pass-env MODEL_PROVIDER_API_KEY",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, value)

    def test_manual_opencode_binding_and_test_baseline_are_clear(self) -> None:
        for marker in (
            "OPENCODE_CONFIG_DIR",
            "cplt --agent opencode",
            '--allow-read "$CONFIG_DIR"',
            "--pass-env OPENCODE_CONFIG_DIR",
            "-- --agent grillmester",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.guide)

        baseline_heading = "### Installer den eksakte testbaselinen manuelt"
        bundle_heading = "### Hent og verifiser en Grillmester-bundle"
        self.assertLess(self.guide.index(baseline_heading), self.guide.index(bundle_heading))
        baseline = self.guide.split(baseline_heading, 1)[1].split(bundle_heading, 1)[0]
        bundle = self.guide.split(bundle_heading, 1)[1].split(
            "## Hva launcheren faktisk gjør", 1
        )[0]
        self.assertIn("opencode-ai@1.18.20", baseline)
        self.assertIn("reproduserbar CI-evidens", baseline)
        self.assertIn("ikke som runtimekrav", baseline)
        self.assertIn("ingen OpenCode-, Copilot- eller cplt-binær", bundle)

    def test_local_setup_covers_both_clients_and_focused_default(self) -> None:
        recommended = self.local_models.split(
            "## Anbefalt flyt: ett lokalt oppsett, begge terminalklienter", 1
        )[1].split("## Qwen3.8-27B", 1)[0]
        value = normalized(recommended)

        for marker in (
            "grillmester local setup",
            "grillmester local --client copilot",
            "grillmester local --client opencode",
            "grillmester local --full --agent grillmester",
            "focused Barista",
            "grillmester local doctor",
            "OpenCode og Copilot CLI på `PATH`",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, value)

        self.assertIn("binder inferensen til én eksplisitt loopbackprovider", normalized(self.local_models))
        self.assertIn("Grillmester eier ikke serveren", normalized(self.local_models))

    def test_checkout_commands_are_executable_without_an_installed_launcher(self) -> None:
        local_commands = (
            "python3 /absolute/path/to/grillmester/scripts/grillmester.py local setup",
            "python3 /absolute/path/to/grillmester/scripts/grillmester.py local doctor",
            "python3 /absolute/path/to/grillmester/scripts/grillmester.py local launch",
        )
        for name, document in (
            ("installation", self.installation),
            ("local models", self.local_models),
            ("OpenCode", self.guide),
        ):
            value = normalized(document)
            for command in local_commands:
                with self.subTest(document=name, command=command):
                    self.assertIn(command, value)

        for name, document in (
            ("README", self.readme),
            ("installation", self.installation),
        ):
            value = normalized(document)
            for command in (
                "python3 /absolute/path/to/grillmester/scripts/grillmester.py",
                "python3 /absolute/path/to/grillmester/scripts/grillmester.py doctor",
            ):
                with self.subTest(document=name, command=command):
                    self.assertIn(command, value)

        readme = normalized(self.readme)
        self.assertIn(local_commands[0], readme)
        self.assertIn(local_commands[2], readme)
        self.assertIn("OpenAI-kompatibel modellserver", readme)
        for document in (self.readme, self.installation, self.local_models, self.guide):
            with self.subTest(consumer_repo=document[:40]):
                self.assertIn("cd /path/to/consumer-repo", document)

    def test_focused_roster_and_measurement_history_are_honest(self) -> None:
        focused = normalized(self.adrs["0005"])
        for marker in (
            "`grillmester-issue-management`",
            "nøyaktig sju OpenCode-commands",
            "opprinnelige seks-skill-baselinen",
            "ikke en måling av dagens sju-skill-roster",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, focused)

        self.assertIn(
            "opprinnelige focused-rosteren med seks skills",
            normalized(self.local_models),
        )

    def test_local_launcher_keeps_host_home_and_isolates_client_state(self) -> None:
        for name, document in (
            ("installation", self.installation),
            ("local models", self.local_models),
            ("ADR 0005", self.adrs["0005"]),
        ):
            value = normalized(document)
            with self.subTest(document=name):
                self.assertIn("hostens `HOME`", value)
                self.assertRegex(value, r"XDG.*(?:state|klientstate)")
                self.assertNotIn("privat HOME", value)

    def test_issue_creation_is_guarded_in_cplt_and_not_a_global_fallback(self) -> None:
        installation = normalized(self.installation)
        for marker in (
            "cplt-guardede `gh issue`-kommandoer",
            "Det krever ikke en egen write-MCP",
            "repo-scope, `gh`-guard",
            "gjelder ikke automatisk Copilot app, cloud agent",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, installation)

        self.assertNotIn("`cloud-open-weight`", self.local_models)

    def test_manual_copilot_byok_keeps_cplt_path_without_offline_side_mode(self) -> None:
        section = self.local_models.split(
            "## Avansert: manuell Copilot CLI BYOK", 1
        )[1].split("## Copilot app med lokal provider", 1)[0]
        for marker in (
            "grillmester --client copilot --agent barista",
            "--allow-localhost 1234",
            "--pass-env COPILOT_PROVIDER_API_KEY",
            "--disable-builtin-mcps",
            "--secret-env-vars=COPILOT_PROVIDER_API_KEY",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, section)
        self.assertNotIn("COPILOT_OFFLINE", section)
        self.assertNotRegex(section, r"(?m)^copilot\s*$")

    def test_updates_remain_separate_and_launch_has_no_update_check(self) -> None:
        readme = normalized(self.readme)
        installation = normalized(self.installation)
        system_clients = normalized(self.adrs["0004"])

        self.assertIn("`grillmester update` oppdaterer Grillmester", readme)
        self.assertIn("OpenCode, Copilot CLI og cplt følger sine egne pakkekanaler", readme)
        self.assertIn("`brew upgrade grillmester`", installation)
        self.assertIn("Ingen pakkeoperasjon eller oppdateringsforespørsel skjer under vanlig launch", installation)
        self.assertIn("`grillmester update` oppdaterer Grillmester-formelen", system_clients)
        self.assertIn("Vanlig launch gjør fortsatt ingen oppdaterings- eller nettverkskontroll utenfor cplt", system_clients)

    def test_release_runbook_keeps_test_evidence_and_lightweight_tap_updates(self) -> None:
        runbook = normalized(self.release_runbook)
        for marker in (
            "one reviewed bootstrap PR",
            "not one PR per Grillmester release",
            "ordinary Grillmester releases require no maintainer PR",
            "latest non-draft, non-prerelease",
            "Apple Silicon and Intel",
            "exact three-asset roster",
            "OpenCode-TUI startup through cplt without a model call",
            "reproducible release-test input, not local-launcher runtime pins",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, runbook)
        self.assertNotIn("upstream-client-watch", self.release_runbook)
        self.assertNotIn("watch_upstream_clients.py", self.release_runbook)

    def test_client_bootstrap_and_runtime_support_boundaries_are_explicit(self) -> None:
        trust = normalized(self.trust)
        guide = normalized(self.guide)
        installation = normalized(self.installation)

        self.assertIn("Homebrew-checksum binder Grillmester-bundle-en, ikke disse klientbinærene", trust)
        self.assertIn("release-gatekode, ikke runtimepinner", trust)
        self.assertIn("OpenCode 1.18.20 forsøker å skrive `.gitignore`", guide)
        self.assertIn("Endre aldri en eksisterende brukerfil automatisk", guide)
        self.assertIn("den eksakte targetfilen fra testbaselinen", installation)


class DocumentationAnchorIntegrityTest(unittest.TestCase):
    """Every intra-repository markdown fragment link must hit a real heading."""

    LINK = re.compile(r"\]\(([^)#\s]*\.md)?#([^)\s]+)\)")

    @staticmethod
    def _slugify(heading: str) -> str:
        text = heading.strip().lower()
        text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
        return re.sub(r"\s+", "-", text)

    def test_internal_documentation_anchors_resolve(self) -> None:
        documents = [
            ROOT / "README.md",
            *sorted((ROOT / "docs").glob("*.md")),
            *sorted((ROOT / "docs/adr").glob("*.md")),
        ]
        anchors: dict[Path, set[str]] = {}
        for document in documents:
            headings = re.findall(
                r"^#{1,6}\s+(.*)$",
                document.read_text(encoding="utf-8"),
                flags=re.MULTILINE,
            )
            anchors[document] = {self._slugify(heading) for heading in headings}
        for document in documents:
            content = document.read_text(encoding="utf-8")
            for target_name, fragment in self.LINK.findall(content):
                if target_name.startswith(("http://", "https://")):
                    continue
                target = (
                    (document.parent / target_name).resolve()
                    if target_name
                    else document
                )
                with self.subTest(source=document.name, link=f"{target_name}#{fragment}"):
                    self.assertIn(
                        target,
                        anchors,
                        f"{document} links to unknown document {target_name}",
                    )
                    self.assertIn(
                        fragment,
                        anchors[target],
                        f"{document} links to missing anchor #{fragment} in "
                        f"{target.name}",
                    )


if __name__ == "__main__":
    unittest.main()
