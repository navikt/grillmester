#!/usr/bin/env python3
"""Measure which skills a real model loads for ordinary requests.

Each run starts a fresh Copilot CLI session in a disposable repository with an
isolated home, and stops after a few tool calls. The runs make real model
requests, so they cost AI credits. Results hold names and counts, never
conversation content.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
MAX_TOOL_CALLS = 15
RUN_TIMEOUT_SECONDS = 150
SYSTEM_PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
GIT_ENVIRONMENT = {
    "GIT_AUTHOR_NAME": "Rutingstest",
    "GIT_AUTHOR_EMAIL": "rutingstest@example.invalid",
    "GIT_COMMITTER_NAME": "Rutingstest",
    "GIT_COMMITTER_EMAIL": "rutingstest@example.invalid",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}


@dataclass(frozen=True)
class Scenario:
    id: str
    prompt: str
    expected: tuple[str, ...]
    agent: str = "grillmester"


SCENARIOS = (
    Scenario(
        "grilling",
        "Vi vil la saksbehandlere trekke tilbake et vedtak, men jeg er usikker på "
        "hva det betyr for historikk og varsler. Hjelp meg å finne ut hvordan det "
        "bør virke.",
        ("grilling",),
    ),
    Scenario(
        "domain-modeling",
        "Koden bruker både vedtak og beslutning om det samme. Rydd opp i begrepene "
        "og skriv ned hva som gjelder.",
        ("domain-modeling",),
    ),
    Scenario(
        "wayfinder",
        "Vi skal bytte ut saksflyten. Leverandørens muligheter styrer datamodellen, "
        "og den styrer migrering og utrulling. Hold styr på disse beslutningene over "
        "flere økter.",
        ("wayfinder",),
    ),
    Scenario(
        "tdd",
        "Legg til validering som avviser vedtak uten begrunnelse, og skriv testen "
        "først.",
        ("tdd",),
    ),
    Scenario(
        "diagnosing-bugs",
        "VedtakServiceTest feiler av og til på CI, men aldri lokalt. Jeg skjønner "
        "ikke hvorfor. Finn årsaken.",
        ("diagnosing-bugs",),
    ),
    Scenario(
        "review",
        "Se over endringene på denne branchen mot main før jeg går videre.",
        ("review",),
    ),
    Scenario(
        "security-review",
        "Det nye endepunktet returnerer fødselsnummer og vedtaksgrunnlag. Gjør en "
        "sikkerhetsvurdering før vi går i produksjon.",
        ("security-review",),
    ),
    Scenario(
        "pull-request",
        "Endringene er ferdige. Skriv PR-teksten for denne branchen.",
        ("pull-request",),
    ),
    Scenario(
        "to-spec",
        "Retningen er avklart: et vedtak kan trekkes tilbake innen 14 dager. Skriv "
        "en spesifikasjon vi kan dele med teamet.",
        ("to-spec",),
    ),
    Scenario(
        "to-issues",
        "Planen ligger i docs/plan.md. Del den opp i issues vi kan jobbe med hver "
        "for oss.",
        ("issue-management",),
    ),
    Scenario(
        "triage",
        "Vi har fått en feilrapport om at varsler kommer dobbelt. Vurder om den er "
        "klar til å jobbes med.",
        ("issue-management",),
    ),
    Scenario(
        "issue-management",
        "Opprett et issue for feilen med manglende begrunnelse.",
        ("issue-management",),
    ),
    Scenario(
        "api-design",
        "Andre team skal hente vedtak fra oss. Hvordan bør REST-API-et utformes?",
        ("nav-platform",),
    ),
    Scenario(
        "auth-overview",
        "Hvordan validerer vi TokenX-tokens i denne tjenesten, og hvilke claims må "
        "vi sjekke?",
        ("nav-platform",),
    ),
    Scenario(
        "kafka-topic",
        "Vi må publisere vedtakshendelser. Sett opp et nytt Kafka-topic på Aiven med "
        "riktige tilganger.",
        ("nav-platform",),
    ),
    Scenario(
        "kotlin-ktor",
        "Legg til et Ktor-endepunkt som henter ett vedtak med id.",
        ("nav-platform",),
    ),
    Scenario(
        "nais-manifest",
        "Appen trenger mer minne og tilgang til en annen tjeneste. Oppdater "
        "Nais-konfigurasjonen.",
        ("nav-platform",),
    ),
    Scenario(
        "nav-troubleshoot",
        "Appen går i CrashLoopBackOff i dev-gcp etter siste deploy. Hva er galt?",
        ("nav-platform",),
    ),
    Scenario(
        "observability-setup",
        "Legg til metrikker og tracing, så vi ser hvor lang tid vedtakene tar.",
        ("nav-platform",),
    ),
    Scenario(
        "postgresql-review",
        "Gå gjennom SQL-migreringen og indeksene for vedtakstabellen. Tåler dette "
        "ti millioner rader?",
        ("nav-platform",),
    ),
    Scenario(
        "architecture-review",
        "Bør vi dele denne tjenesten i to, én for vedtak og én for varsling? Vurder "
        "arkitekturen.",
        ("architecture-review",),
    ),
    Scenario(
        "improve-codebase-architecture",
        "Denne kodebasen er blitt vanskelig å teste og endre. Finn hvor strukturen "
        "bør forbedres.",
        ("improve-codebase-architecture",),
    ),
    Scenario(
        "prototype",
        "Vi er usikre på tilstandene et vedtak kan ha. Lag en rask prototype så vi "
        "kan prøve dem.",
        ("prototype",),
    ),
    Scenario(
        "klarsprak",
        "Gjør denne teksten lettere å forstå for brukerne: «Vedtaket er fattet i "
        "medhold av folketrygdloven.»",
        ("klarsprak",),
    ),
    Scenario(
        "dulting",
        "Mange glemmer å svare på varselet om vedtak. Hvordan kan vi få flere til å "
        "svare i tide uten å presse dem?",
        ("dulting",),
    ),
    Scenario(
        "okr",
        "Formuler mål og måltall for teamet det neste halvåret.",
        ("produktledelse",),
        "doctor-who",
    ),
    Scenario(
        "team-status",
        "Lag en statusoppdatering for teamet denne uka.",
        ("produktledelse",),
        "doctor-who",
    ),
    Scenario(
        "workshop-design",
        "Vi skal ha en workshop om hvordan brukerne opplever vedtaksbrevet. Lag et "
        "opplegg.",
        ("produktledelse",),
        "doctor-who",
    ),
    Scenario(
        "produktledelse",
        "Vi vet lite om hvorfor brukere ringer etter at de har fått vedtak. Hvordan "
        "bør vi utforske dette?",
        ("produktledelse",),
        "doctor-who",
    ),
    Scenario(
        "aksel-design",
        "Velg riktige Aksel-komponenter til skjemaet for å klage på vedtak.",
        ("aksel-design",),
        "designer",
    ),
    Scenario(
        "design-prototype",
        "Utforsk tre ulike layouter for siden der brukeren ser vedtaket.",
        ("design-prototype",),
        "designer",
    ),
    Scenario(
        "figma-workflow",
        "Vi har valgt designet i Figma. Gjør det om til Aksel-kode.",
        ("figma-workflow",),
        "designer",
    ),
    Scenario(
        "accessibility-review",
        "Sjekk at klageskjemaet virker med tastatur og skjermleser.",
        ("accessibility-review",),
        "designer",
    ),
    Scenario(
        "no-skill-typo",
        "Rett skrivefeilen «Vedak» til «Vedtak» i README.md.",
        (),
    ),
    Scenario(
        "no-skill-question",
        "Hva gjør funksjonen fattVedtak i VedtakService?",
        (),
    ),
)

FIXTURE_FILES = {
    "README.md": "# vedtak-api\n\nTjeneste for Vedak om oppfølging.\n",
    "docs/plan.md": (
        "# Plan\n\n1. Legg til status på vedtak.\n2. Send varsel ved ny status.\n"
        "3. Vis status i frontenden.\n"
    ),
    "build.gradle.kts": 'plugins { kotlin("jvm") version "2.2.0" }\n',
    "settings.gradle.kts": 'rootProject.name = "vedtak-api"\n',
    ".nais/app.yaml": (
        "apiVersion: nais.io/v1alpha1\nkind: Application\nmetadata:\n"
        "  name: vedtak-api\n  namespace: team-vedtak\nspec:\n"
        "  image: {{ image }}\n  port: 8080\n"
    ),
    "src/main/kotlin/no/nav/vedtak/Application.kt": (
        "package no.nav.vedtak\n\nimport io.ktor.server.application.*\n"
        "import io.ktor.server.routing.*\n\nfun Application.module() {\n"
        "    routing { vedtakRoutes(VedtakService()) }\n}\n"
    ),
    "src/main/kotlin/no/nav/vedtak/VedtakService.kt": (
        "package no.nav.vedtak\n\nclass VedtakService {\n"
        "    fun fattVedtak(fnr: String, begrunnelse: String?): Vedtak =\n"
        "        Vedtak(fnr, begrunnelse)\n}\n\n"
        "data class Vedtak(val fnr: String, val begrunnelse: String?)\n"
    ),
    "src/main/resources/db/migration/V1__vedtak.sql": (
        "CREATE TABLE vedtak (id UUID PRIMARY KEY, fnr TEXT NOT NULL, "
        "begrunnelse TEXT);\n"
    ),
    "src/test/kotlin/no/nav/vedtak/VedtakServiceTest.kt": (
        "package no.nav.vedtak\n\nimport kotlin.test.Test\n"
        "import kotlin.test.assertEquals\n\nclass VedtakServiceTest {\n"
        "    @Test fun `fatter vedtak`() {\n"
        '        assertEquals("x", VedtakService().fattVedtak("1", "x").begrunnelse)\n'
        "    }\n}\n"
    ),
}
FEATURE_FILE = "src/main/kotlin/no/nav/vedtak/VedtakRoutes.kt"
FEATURE_CONTENT = (
    "package no.nav.vedtak\n\nimport io.ktor.server.response.*\n"
    "import io.ktor.server.routing.*\n\nfun Route.vedtakRoutes(service: VedtakService) {\n"
    '    get("/vedtak") { call.respond(service.fattVedtak("1", null)) }\n}\n'
)


@dataclass
class RunResult:
    scenario: str
    run: int
    agent: str
    model: str
    skills: list[str] = field(default_factory=list)
    tool_calls: int = 0
    used_models: list[str] = field(default_factory=list)
    premium_requests: float | None = None
    stopped: str = "exit"
    seconds: float = 0.0


def write_fixture(root: Path) -> None:
    """Build a small repository with a feature branch ahead of main."""

    def git(*arguments: str) -> None:
        subprocess.run(
            ("git", "-C", str(root), *arguments),
            check=True,
            capture_output=True,
            env={"PATH": SYSTEM_PATH, **GIT_ENVIRONMENT},
        )

    for relative, content in FIXTURE_FILES.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    git("init", "--quiet", "--initial-branch=main")
    git("add", ".")
    git("commit", "--quiet", "-m", "Første versjon")
    git("switch", "--quiet", "-c", "vedtak-endepunkt")
    (root / FEATURE_FILE).write_text(FEATURE_CONTENT, encoding="utf-8")
    git("add", ".")
    git("commit", "--quiet", "-m", "Legg til endepunkt for vedtak")


def copy_plugin_without_model_pins(source: Path, destination: Path) -> None:
    """Let --model decide: an agent's `model` field outranks the flag."""

    shutil.copytree(source, destination)
    for agent in (destination / "agents").glob("*.agent.md"):
        lines = agent.read_text(encoding="utf-8").splitlines(keepends=True)
        agent.write_text(
            "".join(line for line in lines if not line.startswith("model:")),
            encoding="utf-8",
        )


def client_command(
    copilot: str, plugin: Path, scenario: Scenario, model: str
) -> list[str]:
    return [
        copilot,
        "--plugin-dir",
        str(plugin),
        "--agent",
        f"grillmester:{scenario.agent}",
        "--model",
        model,
        "--prompt",
        scenario.prompt,
        "--output-format",
        "json",
        "--allow-all",
        "--secret-env-vars=COPILOT_GITHUB_TOKEN",
        "--no-ask-user",
        "--no-custom-instructions",
        "--no-auto-update",
        "--no-experimental",
        "--disable-builtin-mcps",
    ]


def read_events(lines: Iterable[str], result: RunResult) -> bool:
    """Update the result from JSONL events; return True once it has seen enough."""

    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        kind = event.get("type")
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        if kind == "assistant.turn_end" and result.skills:
            result.stopped = "skill loaded"
            return True
        if kind == "result" and isinstance(event.get("usage"), dict):
            result.premium_requests = event["usage"].get("premiumRequests")
        if kind != "tool.execution_start" or event.get("agentId"):
            continue
        result.tool_calls += 1
        model = data.get("model")
        if isinstance(model, str) and model not in result.used_models:
            result.used_models.append(model)
        arguments = data.get("arguments")
        if data.get("toolName") == "skill" and isinstance(arguments, dict):
            name = arguments.get("skill")
            if isinstance(name, str) and name not in result.skills:
                result.skills.append(name)
        if result.tool_calls >= MAX_TOOL_CALLS:
            result.stopped = "tool limit"
            return True
    return False


def _stop(process: subprocess.Popen[str]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def run_once(
    scenario: Scenario,
    run: int,
    *,
    copilot: str,
    plugin: Path,
    model: str,
    token: str,
) -> RunResult:
    result = RunResult(scenario.id, run, scenario.agent, model)
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="grillmester-routing-") as temporary:
        root = Path(temporary).resolve()
        repository = root / "repo"
        home = root / "home"
        repository.mkdir()
        home.mkdir()
        write_fixture(repository)
        process = subprocess.Popen(
            client_command(copilot, plugin, scenario, model),
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
        timer = threading.Timer(RUN_TIMEOUT_SECONDS, _stop, (process,))
        timer.start()
        try:
            assert process.stdout is not None
            if read_events(process.stdout, result):
                _stop(process)
            process.wait()
            if time.monotonic() - started >= RUN_TIMEOUT_SECONDS:
                result.stopped = "timeout"
        finally:
            timer.cancel()
            _stop(process)
    result.seconds = round(time.monotonic() - started, 1)
    return result


def scenario_hit(scenario: Scenario, skills: Sequence[str]) -> bool:
    if not scenario.expected:
        return not skills
    return any(skill in skills for skill in scenario.expected)


def summarize(
    scenarios: Sequence[Scenario], results: Sequence[RunResult]
) -> list[dict[str, object]]:
    rows = []
    for scenario in scenarios:
        runs = [result for result in results if result.scenario == scenario.id]
        if not runs:
            continue
        loads = Counter(skill for run in runs for skill in run.skills)
        rows.append(
            {
                "scenario": scenario.id,
                "agent": scenario.agent,
                "runs": len(runs),
                "hits": sum(scenario_hit(scenario, run.skills) for run in runs),
                "noSkill": sum(not run.skills for run in runs),
                "loads": dict(loads.most_common()),
            }
        )
    return rows


def render_table(rows: Sequence[Mapping[str, object]]) -> str:
    lines = [
        "| Scenario | Agent | Treff | Uten skill | Lastet |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        loads = row["loads"]
        assert isinstance(loads, dict)
        loaded = ", ".join(f"`{name}` {count}" for name, count in loads.items())
        lines.append(
            f"| `{row['scenario']}` | {row['agent']} | {row['hits']}/{row['runs']} "
            f"| {row['noSkill']} | {loaded or '–'} |"
        )
    return "\n".join(lines) + "\n"


def github_token() -> str:
    token = os.environ.get("COPILOT_GITHUB_TOKEN")
    if token:
        return token
    return subprocess.run(
        ("gh", "auth", "token"), check=True, capture_output=True, text=True
    ).stdout.strip()


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", required=True, help="model to run every session on")
    parser.add_argument("--output", type=Path, required=True, help="directory for results")
    parser.add_argument("--plugin", type=Path, default=ROOT / "plugin")
    parser.add_argument("--runs", type=int, default=10, help="sessions per scenario")
    parser.add_argument("--jobs", type=int, default=4, help="parallel sessions")
    parser.add_argument("--only", nargs="*", help="scenario IDs to run")
    parser.add_argument("--copilot", default="copilot")
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    options = parse_arguments(arguments)
    scenarios = tuple(
        scenario
        for scenario in SCENARIOS
        if not options.only or scenario.id in options.only
    )
    copilot = shutil.which(options.copilot)
    if copilot is None:
        print(f"{options.copilot} was not found", file=sys.stderr)
        return 1
    token = github_token()
    options.output.mkdir(parents=True, exist_ok=True)
    plugin = (options.output / "plugin").resolve()
    if not plugin.exists():
        copy_plugin_without_model_pins(options.plugin.resolve(strict=True), plugin)
    jobs = [
        (scenario, run) for run in range(options.runs) for scenario in scenarios
    ]
    results: list[RunResult] = []
    with (
        (options.output / "runs.jsonl").open("a", encoding="utf-8") as log,
        concurrent.futures.ThreadPoolExecutor(options.jobs) as pool,
    ):
        futures = [
            pool.submit(
                run_once,
                scenario,
                run,
                copilot=copilot,
                plugin=plugin,
                model=options.model,
                token=token,
            )
            for scenario, run in jobs
        ]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            results.append(result)
            log.write(json.dumps(asdict(result), ensure_ascii=False) + "\n")
            log.flush()
            print(
                f"{len(results)}/{len(jobs)} {result.scenario}: "
                f"{', '.join(result.skills) or '-'}",
                flush=True,
            )
    rows = summarize(scenarios, results)
    (options.output / "summary.md").write_text(render_table(rows), encoding="utf-8")
    print(render_table(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
