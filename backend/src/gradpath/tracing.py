"""LangSmith tracing on/off rules: the single place that decides whether anything reaches LangSmith.

Traces hold full prompts (retrieved text, job descriptions, later profiles), so tracing is:
- off unless `LANGSMITH_TRACING=true` in settings AND `LANGSMITH_API_KEY` is set;
- always off in live mode (visitor requests on the deployed site);
- off from the moment this module is imported (retrieval and providers import it), and set
  explicitly in code, which langsmith checks before its own environment variables; so
  `LANGSMITH_TRACING` / `LANGCHAIN_TRACING_V2` in the shell can't switch it on by themselves,
  only through our settings and these rules;
- sent only to the configured endpoint, and refused if `LANGSMITH_RUNS_ENDPOINTS` (extra upload
  destinations) is set;
- redacted client-side before upload (langsmith's secret rules + Voyage keys, emails, phones).
Called once per process by the API lifespan and the CLIs that call models; every other process
(ingest, probe, eval) stays off. See ARCHITECTURE.md,
"Tracing"; the visitor-key guard is in `providers.factory.get_chat_model`.
"""

import logging
import os
import re
from dataclasses import dataclass

import langsmith
from langsmith import Client
from langsmith.anonymizer import create_secret_anonymizer
from langsmith.utils import tracing_is_enabled

from gradpath.config import Settings

log = logging.getLogger(__name__)

REDACTED = "[REDACTED]"
EXTRA_RULES = [
    {"pattern": re.compile(r"\bpa-[A-Za-z0-9_-]{30,}"), "replace": "[SECRET_DETECTED]"},  # Voyage
    {"pattern": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "replace": REDACTED},
    {
        # Needs separators, so scores, ids and years aren't mistaken for phone numbers.
        "pattern": re.compile(
            r"(?<!\w)(?:\+?\d{1,3}[\s.-])?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]\d{4}(?!\w)"
        ),
        "replace": REDACTED,
    },
    {
        # International format with a leading +, e.g. "+44 7911 123456".
        "pattern": re.compile(r"(?<!\w)\+\d{1,3}(?:[\s.-]?\d{2,5}){2,4}(?!\w)"),
        "replace": REDACTED,
    },
]
redact = create_secret_anonymizer(extra_rules=EXTRA_RULES)


@dataclass(frozen=True)
class TracingStatus:
    enabled: bool
    reason: str


_client: Client | None = None


def decide(settings: Settings) -> TracingStatus:
    """The on/off rule alone (no side effects), so it can be tested and logged."""
    if not settings.langsmith_tracing:
        return TracingStatus(False, "LANGSMITH_TRACING is not true")
    if settings.app_mode == "live":
        return TracingStatus(False, "live mode never traces (visitor requests)")
    key = settings.langsmith_api_key
    if key is None or not key.get_secret_value().strip():
        return TracingStatus(False, "LANGSMITH_API_KEY is not set")
    if os.environ.get("LANGSMITH_RUNS_ENDPOINTS"):
        return TracingStatus(False, "LANGSMITH_RUNS_ENDPOINTS is set (extra upload destinations)")
    return TracingStatus(True, f"project {settings.langsmith_project}")


def configure_tracing(settings: Settings) -> TracingStatus:
    """Apply `decide` to the whole process via `langsmith.configure` and log the outcome.

    Off is set explicitly too (`enabled=False`), overriding any environment variable.
    """
    global _client
    status = decide(settings)
    if status.enabled:
        _client = Client(
            # Explicit, so a stray LANGSMITH_ENDPOINT in the shell can't redirect uploads.
            api_url=settings.langsmith_endpoint,
            api_key=settings.langsmith_api_key.get_secret_value(),
            anonymizer=redact,
        )
        langsmith.configure(client=_client, enabled=True, project_name=settings.langsmith_project)
    else:
        _client = None
        langsmith.configure(client=None, enabled=False)
    log.info("LangSmith tracing %s (%s)", "on" if status.enabled else "off", status.reason)
    return status


def is_tracing() -> bool:
    """True if a traced run would be sent right now (used by the visitor-key guard)."""
    return bool(tracing_is_enabled())


# Off until configure_tracing says otherwise, so processes that never call it can't trace.
langsmith.configure(client=None, enabled=False)


def flush() -> None:
    """Send queued traces before a short-lived process exits (CLIs, API shutdown)."""
    if _client is not None:
        _client.flush()
