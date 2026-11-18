"""Prompt-injection helpers shared by every prompt that wraps untrusted text in tags."""

import re


def neutralise_tags(text: str, tags: tuple[str, ...]) -> str:
    """Turn `<tag` / `</tag` for our delimiter tags into harmless `&lt;tag` / `&lt;/tag`.

    Untrusted text (retrieved chunks, job descriptions, user questions) is wrapped in tags such as
    `<evidence>` or `<job_description>`; if the text contained those tags itself it could close its
    block and pose as instructions. Used by rag/answer.py and jobs/analyze.py.
    """
    pattern = re.compile(r"<(/?)\s*(" + "|".join(map(re.escape, tags)) + r")\b", re.IGNORECASE)
    return pattern.sub(lambda m: f"&lt;{m.group(1)}{m.group(2)}", text)
