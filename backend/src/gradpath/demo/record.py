"""Record the demo runs: real calls on the sample posting and profile, into `demo_runs/` (T-018).

Run from `backend/` in your own terminal (Claude Code mode), with the API stopped (local Qdrant
allows one process):
  uv run python -m gradpath.demo.record [--only ID ...] [--force] [--list]
Takes no file arguments: inputs are always the committed sample posting and the fictional sample
profile, so a real profile can't end up in a public recording. Nothing is traced. Existing files
are kept unless `--force` (saves plan quota and Voyage tokens). Each file is scanned for emails,
phone numbers and key patterns before it is written, and refused if one matches.
"""

import argparse
import json
import re
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel

from gradpath.config import REPO_ROOT, Settings, get_settings
from gradpath.demo.library import RECORDING, AskRecording, JobRecording, PlanRecording
from gradpath.jobs import analyze_job
from gradpath.retrieval import RetrievalService
from gradpath.router.assist import AssistRequest, AssistResponse, decide, respond
from gradpath.tracing import EXTRA_RULES, is_tracing
from gradpath.workflows import CareerPrepResult, UserProfile

SAMPLE_JOB = REPO_ROOT / "evaluation" / "job_descriptions" / "sample_backend_new_grad.txt"
SAMPLE_PROFILE = REPO_ROOT / "evaluation" / "profiles" / "sample_new_grad.json"
PLAN_REQUEST = "Make me a preparation plan for this job."

Recording = AskRecording | JobRecording | PlanRecording


@dataclass(frozen=True)
class Spec:
    """One recording to make. `uses` names an earlier ask whose workflow result a plan reuses,
    so the router's "workflow" example and the Plan example cost one workflow run, not two."""

    id: str
    kind: Literal["ask", "job", "plan"]
    title: str
    summary: str
    message: str = ""
    with_job: bool = False
    with_profile: bool = False
    uses: str | None = None
    # For an ask, the "route/outcome" the router must produce; anything else is refused before
    # saving, because `decide` is a model call and a mislabelled example would mislead visitors.
    expect: str | None = None


SPECS: tuple[Spec, ...] = (
    Spec("ask-multicolumn-indexes", "ask", "How do multicolumn indexes work in PostgreSQL?",
         "A focused question: the router picks traditional RAG and the answer cites the sources.",
         message="How do multicolumn indexes work in PostgreSQL?",
         expect="traditional_rag/answered"),
    Spec("ask-idempotent-endpoints", "ask", "What makes an API endpoint idempotent?",
         "Traditional RAG over the HTTP and API sources.",
         message="What makes an API endpoint idempotent?",
         expect="traditional_rag/answered"),
    Spec("ask-graceful-shutdown", "ask", "How should a service shut down gracefully?",
         "Traditional RAG over the operations sources.",
         message="How should a service shut down gracefully?",
         expect="traditional_rag/answered"),
    Spec("ask-not-covered", "ask", "Kubernetes liveness probes (a known gap)",
         "Near a gap in the knowledge base: the answer gives what the sources cover and says "
         "what they don't.",
         message="How do I configure liveness probes for a Kubernetes deployment?",
         expect="traditional_rag/answered"),
    Spec("ask-needs-profile", "ask", "A plan request without a profile",
         "The router sees a job-preparation request with no profile and asks for it.",
         message=PLAN_REQUEST, with_job=True,
         expect="agentic_workflow/needs_input"),
    Spec("ask-plan-workflow", "ask", "A plan request with posting and profile",
         "The router picks the agentic workflow: gaps, roadmap and interview questions.",
         message=PLAN_REQUEST, with_job=True, with_profile=True,
         expect="agentic_workflow/prepared"),
    Spec("job-sample-backend", "job", "Sample new-grad backend posting",
         "Each requirement with its coverage in the knowledge base and a cited study note.",
         with_job=True),
    Spec("plan-sample-backend", "plan", "Preparation plan: sample posting and profile",
         "The full workflow run for the fictional sample profile.",
         with_job=True, with_profile=True, uses="ask-plan-workflow"),
)  # fmt: skip


def _local_paths() -> list[re.Pattern[str]]:
    """This machine's home and repo folders, in both slash styles and JSON-escaped (an error or
    fallback text could quote one), plus any Windows user folder."""
    roots = {str(Path.home()), str(REPO_ROOT)}
    variants = {v for r in roots for v in (r, r.replace("\\", "/"), r.replace("\\", "\\\\"))}
    return [re.compile(re.escape(v), re.IGNORECASE) for v in variants] + [
        re.compile(r"[A-Za-z]:[\\/]+Users[\\/]", re.IGNORECASE)
    ]


# What a public recording must never contain, by kind (the refusal names the kind, never the
# match): the tracing redactor's rules (emails, phones, Voyage keys), other keys, local paths.
# Fails closed: a study note quoting an email address blocks the recording too.
SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = (
    [("an email address, phone number or Voyage key", rule["pattern"]) for rule in EXTRA_RULES]
    + [
        ("an Anthropic key", re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}")),
        ("a LangSmith key", re.compile(r"lsv2_[a-z]{2}_[A-Za-z0-9_]{20,}")),
        ("a GitHub token", re.compile(r"\b(?:ghp|gho|ghs|github_pat)_[A-Za-z0-9_]{20,}")),
        ("an AWS key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
        ("an API key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}")),
    ]
    + [("a local path", pattern) for pattern in _local_paths()]
)


@dataclass
class Services:
    """What a recording needs; the CLI opens real ones, tests pass fakes."""

    retrieval: RetrievalService
    fast: BaseChatModel
    smart: BaseChatModel
    settings: Settings


def sample_inputs() -> tuple[str, UserProfile]:
    """The committed sample posting and fictional profile (the only inputs ever recorded)."""
    job = SAMPLE_JOB.read_text(encoding="utf-8")
    profile = UserProfile.model_validate(json.loads(SAMPLE_PROFILE.read_text(encoding="utf-8")))
    return job, profile


def find_secret(text: str) -> str | None:
    """What kind of secret or personal detail `text` holds (for the refusal), or None if clean."""
    for kind, pattern in SECRET_PATTERNS:
        if pattern.search(text):
            return kind
    return None


def build(
    spec: Spec, services: Services, *, earlier: dict[str, Recording], today: date
) -> Recording:
    """Make one recording through the same functions the API routes call (`decide` + `respond`
    for /api/assist, `analyze_job`, the workflow). A plan reuses an earlier ask's result."""
    job, profile = sample_inputs()
    base = {"id": spec.id, "title": spec.title, "summary": spec.summary, "recorded_at": today}
    if spec.kind == "plan":
        source = earlier.get(spec.uses or "")
        result: CareerPrepResult | None = (
            source.response.result if isinstance(source, AskRecording) else None
        )
        if result is None:
            raise ValueError(f"{spec.id} needs a workflow result from {spec.uses}")
        return PlanRecording(
            kind="plan", job_description=job, profile=profile, result=result, **base
        )
    if spec.kind == "job":
        analysis = analyze_job(job, services.retrieval, services.fast, services.smart)
        return JobRecording(kind="job", job_description=job, analysis=analysis, **base)
    req = AssistRequest(
        message=spec.message,
        job_description=job if spec.with_job else None,
        profile=profile if spec.with_profile else None,
    )
    decision = decide(req, services.fast)
    if spec.expect and spec.expect != f"{decision.route}/{_outcome(decision)}":
        raise ValueError(
            f"{spec.id}: the router chose {decision.route}/{decision.action} "
            f"({decision.kind}), expected {spec.expect}; nothing saved"
        )
    response: AssistResponse = respond(
        req, decision, retrieval=services.retrieval, fast_llm=services.fast,
        smart_llm=services.smart, settings=services.settings,
    )  # fmt: skip
    return AskRecording(
        kind="ask",
        message=req.message,
        job_description=req.job_description,
        profile=req.profile,
        response=response,
        **base,
    )


def _outcome(decision) -> str:
    """The outcome `respond` will give a decision (checked before any answer or workflow runs)."""
    if decision.action != "run":
        return decision.action
    return "answered" if decision.route == "traditional_rag" else "prepared"


def save(recording: Recording, folder: Path) -> Path:
    """Scan, re-validate and write one recording atomically (temp file, then rename). A failed
    write removes its temp file, so no half-written `.json.tmp` is left behind (the library only
    reads `*.json`, so a leftover from a killed process is ignored and overwritten next time)."""
    text = recording.model_dump_json(indent=2) + "\n"
    hit = find_secret(text)
    if hit is not None:
        raise ValueError(f"{recording.id}: refused, the output contains {hit}; nothing saved")
    RECORDING.validate_json(text)  # what the API will load must be what we wrote
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{recording.id}.json"
    tmp = path.with_suffix(".json.tmp")
    try:
        tmp.write_text(text, encoding="utf-8", newline="\n")
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return path


def load_existing(spec_id: str, folder: Path) -> Recording | None:
    """An already-saved recording (so `--only plan-...` can reuse the saved workflow ask).
    A corrupt or outdated file counts as missing, so the run (or `--force`) can replace it."""
    path = folder / f"{spec_id}.json"
    if not path.is_file():
        return None
    try:
        return RECORDING.validate_json(path.read_bytes())
    except ValueError:  # pydantic's ValidationError is a ValueError
        return None


def record_all(
    specs: tuple[Spec, ...],
    services: Callable[[], Services],
    folder: Path,
    *,
    force: bool = False,
    today: date | None = None,
    echo: Callable[[str], None] = print,
    all_specs: tuple[Spec, ...] = SPECS,
) -> list[str]:
    """Record each spec in order, skipping saved files unless `force`. Services are opened only
    when something needs recording. A plan whose source ask was re-recorded in this run is
    rebuilt too, so the two never disagree; one left out of the run is named in a warning.
    Returns the ids written."""
    today = today or date.today()
    earlier: dict[str, Recording] = {}
    opened: Services | None = None
    written: list[str] = []
    for spec in specs:
        existing = None if force else load_existing(spec.id, folder)
        if spec.uses in written:
            existing = None  # its source changed in this run
        if existing is not None:
            earlier[spec.id] = existing
            echo(f"{spec.id}: kept (exists; --force to re-record)")
            continue
        if spec.uses and spec.uses not in earlier:
            saved = load_existing(spec.uses, folder)
            if saved is not None:
                earlier[spec.uses] = saved
        if opened is None and spec.kind != "plan":
            opened = services()
        start = time.monotonic()
        recording = build(spec, opened, earlier=earlier, today=today)  # type: ignore[arg-type]
        save(recording, folder)
        earlier[spec.id] = recording
        written.append(spec.id)
        echo(f"{spec.id}: saved ({describe(recording)}, {time.monotonic() - start:.0f}s)")
        if "fallback" in describe(recording):
            echo(f"{spec.id}: WARNING, a fallback run; check it before committing, or --force")
    ran = {s.id for s in specs}
    for s in all_specs:
        if s.uses in written and s.id not in ran:
            echo(f"WARNING: {s.id} reuses {s.uses}; re-record it: --only {s.id} --force")
    return written


def describe(recording: Recording) -> str:
    """A short status for the terminal: what the owner should check before committing."""
    if isinstance(recording, AskRecording):
        r = recording.response
        status = r.answer.status if r.answer else (r.result.status if r.result else "")
        return f"{r.decision.route}/{r.outcome}" + (f"/{status}" if status else "")
    if isinstance(recording, JobRecording):
        return f"{len(recording.analysis.requirements)} requirements"
    return f"status {recording.result.status}"


def main() -> None:
    """Parse arguments, open real services lazily, record, close Qdrant."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="+", metavar="ID", help="record just these ids")
    parser.add_argument("--force", action="store_true", help="re-record existing files")
    parser.add_argument("--list", action="store_true", help="list the ids and exit")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if args.list:
        for s in SPECS:
            print(f"{s.id:28} {s.kind:5} {s.title}")
        return
    specs = SPECS
    if args.only:
        unknown = set(args.only) - {s.id for s in SPECS}
        if unknown:
            parser.error(f"unknown ids: {', '.join(sorted(unknown))} (see --list)")
        specs = tuple(s for s in SPECS if s.id in args.only)

    from gradpath.providers import get_chat_model
    from gradpath.retrieval import get_retrieval_service

    opened: list[Services] = []

    def open_services() -> Services:
        retrieval = get_retrieval_service()
        try:
            s = Services(retrieval, get_chat_model("fast"), get_chat_model("smart"),
                         get_settings())  # fmt: skip
        except Exception:
            retrieval.store.client.close()  # don't keep the Qdrant lock on a failed start
            raise
        opened.append(s)
        return s

    if is_tracing():  # never expected: gradpath.tracing turns it off at import
        sys.exit("refusing to record: LangSmith tracing is on in this process")
    print("tracing: off (recordings are never traced)", file=sys.stderr)
    try:
        record_all(
            specs, open_services, REPO_ROOT / get_settings().demo_runs_path, force=args.force
        )
    finally:
        for s in opened:
            s.retrieval.store.client.close()


if __name__ == "__main__":
    main()
