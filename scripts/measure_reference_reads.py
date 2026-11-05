#!/usr/bin/env python3
"""Measure whether each skill reference is read when its branch applies.

Every disclosed reference has a case: a request that reaches it. Each run starts
a fresh Copilot CLI session in a disposable repository with an isolated home and
tells the model to use the skill, so the run measures the step from a loaded
skill to its reference. `--natural` leaves that instruction out. The runs make
real model requests, so they cost AI credits. Results hold names and counts,
never conversation content.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]


def _load_sibling(name: str, filename: str):
    specification = importlib.util.spec_from_file_location(
        name, Path(__file__).with_name(filename)
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


ROUTING = _load_sibling("grillmester_routing_for_references", "measure_skill_routing.py")
SKILLS = _load_sibling("grillmester_skill_references_for_reads", "skill_references.py")

MAX_TOOL_CALLS = 12
RUN_TIMEOUT_SECONDS = 170
EDIT_TOOLS = frozenset({"apply_patch", "create", "edit", "write"})
FINGERPRINT_LINES = 3
FINGERPRINT_MINIMUM = 45
CONTENTS_HEADINGS = ("Contents", "Innhold")
USE_SKILL = "\n\nBruk skillen `{skill}`."
DESIGNER = "designer"
DOCTOR = "doctor-who"


@dataclass(frozen=True)
class Case:
    skill: str
    reference: str
    prompt: str
    agent: str = "grillmester"

    @property
    def id(self) -> str:
        return f"{self.skill}/{self.reference}"


CASES = (
    Case(
        "aksel-design",
        "references/patterns.md",
        "Lag en responsiv side med sidemeny og kort-grid i VedtakSide.tsx.",
        DESIGNER,
    ),
    Case(
        "app-sandbox-setup",
        "references/maintenance.md",
        "Hvordan ruller jeg tilbake sandkasseoppsettet, og hvor er "
        "sikkerhetskopiene?",
    ),
    Case(
        "app-sandbox-setup",
        "references/risks.md",
        "Sett opp sandkassen. Hvilke valg må jeg ta om maskering og Docker?",
    ),
    Case(
        "app-sandbox-setup",
        "references/session-history.md",
        "Jeg vil bare oppdatere delt økthistorikk.",
    ),
    Case(
        "app-sandbox-setup",
        "references/toolchain.md",
        "Java og pnpm feiler i sandkassen. Hva gjør jeg?",
    ),
    Case(
        "architecture-review",
        "references/nav-context.md",
        "Vi vurderer å skille ut vedtak som en egen tjeneste på Nais som andre "
        "team skal kalle. Vurder forslaget.",
    ),
    Case(
        "architecture-review",
        "references/review-checklist.md",
        "Vi vil bytte fra Postgres til hendelseslogg som eneste datakilde. Det "
        "blir dyrt å snu. Vurder forslaget.",
    ),
    Case(
        "create-a-skill",
        "references/copilot-cli-validation.md",
        "Jeg har skrevet en ny skill i .github/skills/vedtak-lint. Valider at "
        "Copilot CLI finner og bruker den.",
    ),
    Case(
        "create-a-skill",
        "references/glossary.md",
        "Skillen vår stopper arbeidet for tidlig. Hva er feilmodusen, og "
        "hvordan definerer dere den?",
    ),
    Case(
        "create-a-skill",
        "references/principles.md",
        "Lag en ny skill som hjelper oss å skrive gode vedtaksbrev.",
    ),
    Case(
        "design-prototype",
        "references/aksel-figma-katalog.md",
        "Finn riktig Aksel-komponent og variantakser i Figma for en "
        "statusmelding på vedtakssiden.",
        DESIGNER,
    ),
    Case(
        "design-prototype",
        "references/aksel-figma-tokens.md",
        "Bygg et vedtakskort i Figma med Aksel-spacing og typografi.",
        DESIGNER,
    ),
    Case(
        "design-prototype",
        "references/application-opening.md",
        "Jeg vil se to retninger for vedtakssiden side om side.",
        DESIGNER,
    ),
    Case(
        "design-prototype",
        "references/design-handoff.md",
        "Behold forslaget, og lag en brief til utviklerne.",
        DESIGNER,
    ),
    Case(
        "design-prototype",
        "references/figma-prototype.md",
        "Lag et redigerbart Figma-design av vedtakssiden.",
        DESIGNER,
    ),
    Case(
        "diagnosing-bugs",
        "references/data-access.md",
        "Vedtak feiler sporadisk i prod. Les loggene og finn årsaken.",
    ),
    Case(
        "domain-modeling",
        "ADR-FORMAT.md",
        "Skriv en ADR om at vedtakshendelser går over Kafka.",
    ),
    Case(
        "domain-modeling",
        "GLOSSARY-FORMAT.md",
        "Legg inn begrepet vedtak i GLOSSARY.md.",
    ),
    Case(
        "dulting",
        "references/behavioral-patterns.md",
        "Kartlegg brukerreisen og bruk EAST for å få flere til å svare på "
        "varselet.",
    ),
    Case(
        "dulting",
        "references/ethics-and-evaluation.md",
        "Mange glemmer å svare på varselet om vedtak. Foreslå en påminnelse vi kan"
        " teste.",
    ),
    Case(
        "improve-codebase-architecture",
        "HTML-REPORT.md",
        "Finn refaktoreringsmuligheter i koden og presenter kandidatene.",
    ),
    Case(
        "issue-management",
        "references/AGENT-BRIEF.md",
        "Vurder dette issuet: Vedtak mangler status i API-et. Er det klart til å"
        " jobbes med?",
    ),
    Case(
        "issue-management",
        "references/to-issues.md",
        "Planen ligger i docs/plan.md. Del den opp i issues vi kan jobbe med hver"
        " for oss.",
    ),
    Case(
        "issue-management",
        "references/triage.md",
        "Vi har fått en feilrapport om at varsler kommer dobbelt. Vurder den.",
    ),
    Case(
        "klarsprak",
        "references/ai-markorer.md",
        "Språkvask README.md. Teksten høres KI-generert ut.",
    ),
    Case(
        "klarsprak",
        "references/fagtermer-og-anglisismer.md",
        "Skal vi skrive deploye eller rulle ut i brukerveiledningen? Rett "
        "begrepene i README.md.",
    ),
    Case(
        "klarsprak",
        "references/for-og-etter.md",
        "Skriv om setningen «Det vil bli foretatt en vurdering av saken» og vis"
        " før og etter.",
    ),
    Case(
        "nav-platform",
        "references/api.md",
        "Andre team skal hente vedtak fra oss. Hvordan bør REST-API-et "
        "utformes?",
    ),
    Case(
        "nav-platform",
        "references/auth.md",
        "Hvordan validerer vi TokenX-tokens i denne tjenesten, og hvilke claims"
        " må vi sjekke?",
    ),
    Case(
        "nav-platform",
        "references/database.md",
        "Gå gjennom SQL-migreringen og indeksene for vedtakstabellen. Tåler "
        "dette ti millioner rader?",
    ),
    Case(
        "nav-platform",
        "references/diagnosis.md",
        "Appen går i CrashLoopBackOff i dev-gcp etter siste deploy. Hva er "
        "galt?",
    ),
    Case(
        "nav-platform",
        "references/kafka.md",
        "Vi må publisere vedtakshendelser. Sett opp et nytt Kafka-topic på "
        "Aiven med riktige tilganger.",
    ),
    Case(
        "nav-platform",
        "references/ktor.md",
        "Legg til et Ktor-endepunkt som henter ett vedtak med id.",
    ),
    Case(
        "nav-platform",
        "references/local-auth-mock.md",
        "Integrasjonstestene våre trenger gyldige tokens. Sett opp en mock-"
        "utsteder.",
    ),
    Case(
        "nav-platform",
        "references/nais.md",
        "Appen trenger mer minne og tilgang til en annen tjeneste. Oppdater "
        "Nais-konfigurasjonen.",
    ),
    Case(
        "nav-platform",
        "references/naisjob-example.md",
        "Vi trenger en jobb på Nais som rydder gamle vedtak hver natt.",
    ),
    Case(
        "nav-platform",
        "references/observability.md",
        "Legg til metrikker og tracing, så vi ser hvor lang tid vedtakene tar.",
    ),
    Case(
        "nav-platform",
        "references/plain-kafka.md",
        "Skriv en konsument med kafka-clients direkte, med SSL-oppsettet fra "
        "Nais.",
    ),
    Case(
        "produktledelse",
        "references/discovery.md",
        "Vi vil la brukere trekke tilbake søknader. Hvilke antakelser bør vi teste"
        " først?",
        DOCTOR,
    ),
    Case(
        "produktledelse",
        "references/foundation-sprint.md",
        "Nytt team trenger en felles hypotese. Design en workshop.",
        DOCTOR,
    ),
    Case(
        "produktledelse",
        "references/okr-eksempler.md",
        "Vi skal lage OKR for vedtaksteamet. Lag et utkast.",
        DOCTOR,
    ),
    Case(
        "produktledelse",
        "references/okr.md",
        "Formuler mål og måltall for teamet det neste halvåret.",
        DOCTOR,
    ),
    Case(
        "produktledelse",
        "references/projects-v2.md",
        "Lag status fra GitHub Projects-tavlen vår for denne uken.",
        DOCTOR,
    ),
    Case(
        "produktledelse",
        "references/rapportmaler.md",
        "Skriv ukestatus for teamet.",
        DOCTOR,
    ),
    Case(
        "produktledelse",
        "references/ressurser.md",
        "Hvilke ressurser anbefaler du for å lære brukerintervju?",
        DOCTOR,
    ),
    Case(
        "produktledelse",
        "references/retro-og-teamhelse.md",
        "Design en retro om teamhelse.",
        DOCTOR,
    ),
    Case(
        "produktledelse",
        "references/team-rammeverk.md",
        "Hva betyr forkortelsen PO-MVP i teamet vårt? Den står i planen.",
        DOCTOR,
    ),
    Case(
        "produktledelse",
        "references/team-status.md",
        "Hvordan ligger vi an mot målene denne perioden?",
        DOCTOR,
    ),
    Case(
        "produktledelse",
        "references/workshop.md",
        "Design en halvdags samling der teamet blir enige om prioriteringene.",
        DOCTOR,
    ),
    Case(
        "security-review",
        "references/nav-security-review.md",
        "Sikkerhetsvurder endringen. Vi logger fnr og endrer tilgangskontroll.",
    ),
    Case(
        "security-review",
        "references/threat-model.md",
        "Vi åpner et nytt eksternt API for vedtak. Lag en trusselmodell.",
    ),
    Case(
        "tdd",
        "mocking.md",
        "VedtakService skal kalle et eksternt API. Skriv testen først. Hva skal"
        " mockes?",
    ),
    Case(
        "tdd",
        "test-boundaries.md",
        "Ny regel i VedtakService. Hvilken søm bør testene ligge på?",
    ),
    Case(
        "wayfinder",
        "references/tracker.md",
        "Vi har flere avhengige beslutninger om vedtaksflyten. Lag et delt kart"
        " som issues.",
    ),
)

FRONTEND_FILES = {
    "frontend/package.json": (
        '{\n  "name": "vedtak-frontend",\n  "dependencies": {\n'
        '    "@navikt/ds-css": "^8.0.0",\n    "@navikt/ds-react": "^8.0.0",\n'
        '    "react": "^19.0.0"\n  }\n}\n'
    ),
    "frontend/src/VedtakSide.tsx": (
        'import { Heading } from "@navikt/ds-react";\n\n'
        "export function VedtakSide() {\n"
        '  return <Heading size="large">Vedtak</Heading>;\n}\n'
    ),
}


@dataclass
class ReadResult:
    case: str
    run: int
    loaded: bool = False
    references: list[str] = field(default_factory=list)
    tool_calls: int = 0
    first_reads: dict[str, int] = field(default_factory=dict)
    first_edit: int | None = None
    premium_requests: float | None = None
    stopped: str = "exit"
    seconds: float = 0.0

    def mark(self, reference: str) -> None:
        if reference not in self.references:
            self.references.append(reference)
        self.first_reads.setdefault(reference, self.tool_calls)


def is_proof(line: str) -> bool:
    return len(line) >= FINGERPRINT_MINIMUM and not line.startswith(("|", "```", "#"))


def fingerprints(path: Path) -> tuple[str, ...]:
    """Return the lines that prove a reference's text reached the model.

    A pointer can send the agent to one section, so the first prose line of each
    section is a proof too. Reading only the title and contents proves nothing new.
    """

    text = path.read_text(encoding="utf-8")
    lines = (line.strip() for line in text.splitlines())
    proofs = sorted(filter(is_proof, lines), key=len, reverse=True)[:FINGERPRINT_LINES]
    waiting = False
    for line in map(str.strip, SKILLS.prose_lines(text)):
        if line.startswith(("## ", "### ")):
            waiting = line.split(" ", 1)[1] not in CONTENTS_HEADINGS
        elif waiting and is_proof(line):
            proofs.append(line)
            waiting = False
    return tuple(dict.fromkeys(proofs))


def reference_proofs(skill_root: Path) -> dict[str, tuple[str, ...]]:
    return {
        path.relative_to(skill_root).as_posix(): fingerprints(path)
        for path in SKILLS.disclosed_references(skill_root)
    }


def read_events(
    lines: Iterable[str],
    result: ReadResult,
    skill: str,
    proofs: Mapping[str, tuple[str, ...]],
    limit: int = MAX_TOOL_CALLS,
) -> bool:
    """Update the result from JSONL events; return True once it has seen enough."""

    views: dict[object, str] = {}
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict) or event.get("agentId"):
            continue
        kind = event.get("type")
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        if kind == "result" and isinstance(event.get("usage"), dict):
            result.premium_requests = event["usage"].get("premiumRequests")
        if kind in {"skill.invoked", "skill.invoked_ref"} and data.get("name") == skill:
            result.loaded = True
        if kind == "tool.execution_complete":
            viewed = views.pop(data.get("toolCallId"), None)
            if viewed is not None and data.get("success") is True:
                result.mark(viewed)
            payload = data.get("result")
            if isinstance(payload, dict):
                text = str(payload.get("content", ""))
                for reference, proof in proofs.items():
                    if any(item in text for item in proof):
                        result.mark(reference)
            if result.tool_calls >= limit:
                result.stopped = "tool limit"
                return True
        if kind != "tool.execution_start":
            continue
        result.tool_calls += 1
        tool = data.get("toolName")
        arguments = data.get("arguments") if isinstance(data.get("arguments"), dict) else {}
        if tool == "skill" and arguments.get("skill") == skill:
            result.loaded = True
        command = arguments.get("command")
        if tool == "view" or (tool == "str_replace_editor" and command == "view"):
            path = str(arguments.get("path", ""))
            for reference in proofs:
                if path.endswith(f"/{skill}/{reference}"):
                    views[data.get("toolCallId")] = reference
        edits = tool in EDIT_TOOLS or (tool == "str_replace_editor" and command != "view")
        if edits and result.first_edit is None:
            result.first_edit = result.tool_calls
    return False


def open_manual_skills(plugin: Path) -> None:
    """A manual skill cannot be reached from --prompt; open the measured copy."""

    for path in plugin.glob("skills/*/SKILL.md"):
        text = path.read_text(encoding="utf-8")
        frontmatter = text.split("---", 2)[1]
        if "disable-model-invocation: true" in frontmatter:
            path.write_text(
                text.replace("disable-model-invocation: true\n", "", 1),
                encoding="utf-8",
            )


def write_repository(root: Path) -> None:
    for relative, content in FRONTEND_FILES.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    ROUTING.write_fixture(root)


def run_once(
    case: Case,
    run: int,
    *,
    copilot: str,
    plugin: Path,
    model: str,
    token: str,
    natural: bool,
) -> ReadResult:
    result = ReadResult(case.id, run)
    started = time.monotonic()
    prompt = case.prompt if natural else case.prompt + USE_SKILL.format(skill=case.skill)
    scenario = ROUTING.Scenario(case.id, prompt, (case.skill,), case.agent)
    proofs = reference_proofs(plugin / "skills" / case.skill)
    with tempfile.TemporaryDirectory(prefix="grillmester-references-") as temporary:
        root = Path(temporary).resolve()
        repository = root / "repo"
        home = root / "home"
        repository.mkdir()
        home.mkdir()
        write_repository(repository)
        process = subprocess.Popen(
            ROUTING.client_command(copilot, plugin, scenario, model),
            cwd=repository,
            env={
                "COPILOT_GITHUB_TOKEN": token,
                "COPILOT_HOME": str(home / ".copilot"),
                "HOME": str(home),
                "PATH": "/usr/bin:/bin",
                "PWD": str(repository),
                "TMPDIR": str(root),
            },
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            start_new_session=True,
        )
        timer = threading.Timer(RUN_TIMEOUT_SECONDS, ROUTING._stop, (process,))
        timer.start()
        try:
            assert process.stdout is not None
            if read_events(process.stdout, result, case.skill, proofs):
                ROUTING._stop(process)
            process.wait()
            if time.monotonic() - started >= RUN_TIMEOUT_SECONDS:
                result.stopped = "timeout"
            elif process.returncode and result.stopped == "exit":
                result.stopped = f"exit {process.returncode}"
        finally:
            timer.cancel()
            ROUTING._stop(process)
    result.seconds = round(time.monotonic() - started, 1)
    return result


def read_before_edit(result: ReadResult, reference: str) -> bool:
    first = result.first_reads.get(reference)
    if first is None:
        return False
    return result.first_edit is None or first < result.first_edit


def render_table(cases: Sequence[Case], results: Sequence[ReadResult]) -> str:
    grouped: dict[str, list[ReadResult]] = defaultdict(list)
    for result in results:
        grouped[result.case].append(result)
    rows = [
        "| Referanse | Lastet | Lest | Før første endring | Leste også |",
        "| --- | --- | --- | --- | --- |",
    ]
    read = total = 0
    for case in cases:
        runs = grouped.get(case.id, [])
        loaded = sum(result.loaded for result in runs)
        hits = sum(case.reference in result.references for result in runs)
        early = sum(read_before_edit(result, case.reference) for result in runs)
        also = Counter(
            Path(reference).name
            for result in runs
            for reference in result.references
            if reference != case.reference
        )
        extra = ", ".join(f"`{name}` {count}" for name, count in also.most_common(3))
        rows.append(
            f"| `{case.id}` | {loaded}/{len(runs)} | {hits}/{len(runs)} "
            f"| {early}/{len(runs)} | {extra or '–'} |"
        )
        read += hits
        total += len(runs)
    rows.append(f"| **Sum** | | **{read}/{total}** | | |")
    return "\n".join(rows) + "\n"


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", required=True, help="model to run every session on")
    parser.add_argument("--output", type=Path, required=True, help="directory for results")
    parser.add_argument("--plugin", type=Path, default=ROOT / "plugin")
    parser.add_argument("--runs", type=int, default=3, help="sessions per reference")
    parser.add_argument("--jobs", type=int, default=6, help="parallel sessions")
    parser.add_argument("--only", nargs="*", help="skill or skill/reference IDs to run")
    parser.add_argument("--natural", action="store_true", help="do not name the skill")
    parser.add_argument("--copilot", default="copilot")
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    options = parse_arguments(arguments)
    cases = tuple(
        case
        for case in CASES
        if not options.only or case.id in options.only or case.skill in options.only
    )
    if not cases:
        print("no case matches --only", file=sys.stderr)
        return 1
    copilot = shutil.which(options.copilot)
    if copilot is None:
        print(f"{options.copilot} was not found", file=sys.stderr)
        return 1
    plugin = (options.output / "plugin").resolve()
    if plugin.exists():
        print(f"{options.output} holds an older copy; use a new directory", file=sys.stderr)
        return 1
    token = ROUTING.github_token()
    options.output.mkdir(parents=True, exist_ok=True)
    ROUTING.copy_plugin_without_model_pins(options.plugin.resolve(strict=True), plugin)
    open_manual_skills(plugin)
    jobs = [(case, run) for run in range(options.runs) for case in cases]
    results: list[ReadResult] = []
    with (
        (options.output / "runs.jsonl").open("a", encoding="utf-8") as log,
        concurrent.futures.ThreadPoolExecutor(options.jobs) as pool,
    ):
        futures = [
            pool.submit(
                run_once,
                case,
                run,
                copilot=copilot,
                plugin=plugin,
                model=options.model,
                token=token,
                natural=options.natural,
            )
            for case, run in jobs
        ]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            results.append(result)
            log.write(json.dumps(asdict(result), ensure_ascii=False) + "\n")
            log.flush()
            print(
                f"{len(results)}/{len(jobs)} {result.case}: "
                f"{', '.join(result.references) or '-'}",
                flush=True,
            )
    table = render_table(cases, results)
    (options.output / "summary.md").write_text(table, encoding="utf-8")
    print(table)
    failed = [result for result in results if result.stopped.startswith("exit ")]
    if failed:
        print(f"{len(failed)} sessions failed, so their misses mean nothing", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
