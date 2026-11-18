"""Prompt-injection helpers shared by every prompt that wraps untrusted text in tags."""

import html
import re


def neutralise_tags(text: str, tags: tuple[str, ...]) -> str:
    """Turn `<tag` / `</tag` for our delimiter tags into harmless `&lt;tag` / `&lt;/tag`.

    Untrusted text (retrieved chunks, job descriptions, user questions) is wrapped in tags such as
    `<evidence>` or `<job_description>`; if the text contained those tags itself it could close its
    block and pose as instructions. Used by rag/answer.py and jobs/analyze.py.
    """
    # Whitespace is allowed on both sides of the slash (`< /tag`, `</ tag`): a model may still
    # read those as closing tags.
    pattern = re.compile(r"<\s*(/?)\s*(" + "|".join(map(re.escape, tags)) + r")\b", re.IGNORECASE)
    return pattern.sub(lambda m: f"&lt;{m.group(1)}{m.group(2)}", text)


def escape_attr(value: str) -> str:
    """Escape a value placed inside a tag attribute (`source="..."`, `id="..."`).

    Attribute values such as section names come from scraped headings, so a `"` or `>` in them
    could close the attribute and forge markup; `html.escape(quote=True)` turns `& < > " '` into
    entities. Used with `neutralise_tags` by rag/answer.py and jobs/analyze.py.
    """
    return html.escape(value, quote=True)
