"""Deterministic routing rules: decide only the cases that are certain, leave the rest to the model.

Called first by `route.route_request`. A rule may return only two kinds: a plain definition
question (sent to RAG, the cheap and safe path) or a personal preparation request with both inputs
attached. Anything personal, mixed or unusual returns None and goes to the classifier.
"""

import re

from gradpath.router.schemas import Kind, RouteRequest

DEFINITION_START = re.compile(
    r"^(what is|what's|what are|what does|explain|define|how does|how do)\b", re.IGNORECASE
)
PERSONAL = re.compile(r"\b(i|i'm|i've|i'd|me|my|mine|myself)\b", re.IGNORECASE)
PLAN_WORDS = re.compile(
    r"\b(roadmap|plan|prepare|preparation|study|missing|ready|gaps?)\b", re.IGNORECASE
)
# Words that only fit a request about the whole job (T-021). "prepare" and "study" are not enough:
# "how should I prepare for the indexing part of this role?" is about one topic.
WHOLE_JOB_WORDS = re.compile(r"\b(roadmap|plan|missing|gaps?|am i ready)\b", re.IGNORECASE)
# Words that narrow a request to part of the job: never decided by a rule (T-021).
SCOPE_WORDS = re.compile(r"\b(part|parts|section|only|just|specifically|aspect)\b", re.IGNORECASE)
# Words of the request kinds we don't support yet (comparing jobs, resumes, progress), or that try
# to steer routing: never decided by a rule, so the classifier sees them.
HOLD_WORDS = re.compile(
    r"\b(compare|comparison|two|versus|vs|between|better|jobs|postings|resume|cv|cover|rewrite|"
    r"tailor|update|progress|track|route|routing|system|ignore|instructions?)\b",
    re.IGNORECASE,
)
# Words pointing at an attachment ("this posting"): with an input attached, a definition-shaped
# question may really be about it, so the classifier decides.
DEICTIC = re.compile(
    r"\b(this|these|that|attached|posting|job|role|position|profile)\b", re.IGNORECASE
)
SECOND_SENTENCE = re.compile(r"[.!?]\s+\S")
MAX_RULE_CHARS = 200


def rule_kind(req: RouteRequest) -> tuple[Kind, str] | None:
    """(kind, reason) when a rule is certain, else None. The definition rule needs a single
    sentence, so "What is Docker? Also summarise this posting." goes to the classifier. The
    whole-job rule needs a whole-job word and no narrowing word (T-021); "prepare" alone is open."""
    text = " ".join(req.message.split())
    if len(text) > MAX_RULE_CHARS or HOLD_WORDS.search(text) or "<" in text or "{" in text:
        return None
    personal = PERSONAL.search(text) is not None
    plan = PLAN_WORDS.search(text) is not None
    single = text.count("?") <= 1 and not SECOND_SENTENCE.search(text)
    attached = req.has_job_description or req.has_profile
    if (
        DEFINITION_START.match(text)
        and single
        and not personal
        and not plan
        and not (attached and DEICTIC.search(text))
    ):
        return "knowledge_question", "A general definition or explanation question."
    whole_job = WHOLE_JOB_WORDS.search(text) is not None and not SCOPE_WORDS.search(text)
    if personal and whole_job and req.has_job_description and req.has_profile:
        return "job_preparation", "A personal preparation request with job and profile attached."
    return None
